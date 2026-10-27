"""Persistence, transaction and isolation tests against real SQLite sessions."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from inventory.app import create_app
from inventory.catalog import all_items, create_item, create_warehouse, warehouses
from inventory.database import Base, make_engine, make_sessions
from inventory.errors import Conflict, NotFound
from inventory.models import Movement, Stock
from inventory.schemas import MoveCreate
from inventory.stock import adjust, balances, movements


@pytest.fixture
def session():
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    with make_sessions(engine)() as session:
        yield session
    engine.dispose()


def move(delta, item_id=1, warehouse_id=1):
    return MoveCreate(
        item_id=item_id,
        warehouse_id=warehouse_id,
        delta=delta,
        reason="Fixture count",
    )


def seed(session):
    create_item(session, "BOX", "Sample box")
    create_warehouse(session, "NORTH", "North")


def test_database_survives_application_restart(tmp_path):
    url = f"sqlite:///{tmp_path / 'fixture.db'}"
    with TestClient(create_app(url)) as client:
        created = client.post("/items", json={"sku": "A", "name": "Sample"})
        assert created.status_code == 201
        assert created.json()["id"] == 1
    with TestClient(create_app(url)) as client:
        assert client.get("/items").json()["items"] == [
            {"id": 1, "sku": "A", "name": "Sample", "active": True}
        ]
        second = client.post("/items", json={"sku": "B", "name": "Other"})
        assert second.json()["id"] == 2


def test_application_instances_do_not_share_memory():
    with TestClient(create_app("sqlite://")) as first:
        with TestClient(create_app("sqlite://")) as second:
            first.post("/items", json={"sku": "A", "name": "Sample"})
            assert len(first.get("/items").json()["items"]) == 1
            assert second.get("/items").json()["items"] == []


def test_catalog_conflict_rolls_back_session(session):
    seed(session)
    with pytest.raises(Conflict, match="SKU already exists"):
        create_item(session, "BOX", "Duplicate")
    created = create_item(session, "BAG", "Sample bag")
    assert created.id == 2
    assert [row.sku for row in all_items(session)] == ["BOX", "BAG"]


def test_warehouse_conflict_rolls_back_session(session):
    seed(session)
    with pytest.raises(Conflict, match="code already exists"):
        create_warehouse(session, "NORTH", "Duplicate")
    created = create_warehouse(session, "SOUTH", "South")
    assert created.id == 2
    assert [row.code for row in warehouses(session)] == ["NORTH", "SOUTH"]


def test_failed_decrement_leaves_no_audit_record(session):
    seed(session)
    adjust(session, move(5))
    with pytest.raises(Conflict, match="Insufficient"):
        adjust(session, move(-6))
    assert balances(session)[0].quantity == 5
    assert [row.delta for row in movements(session)] == [5]
    assert adjust(session, move(-5))["quantity"] == 0
    assert [row.delta for row in movements(session)] == [5, -5]


def test_first_negative_move_leaves_no_balance_or_audit(session):
    seed(session)
    with pytest.raises(Conflict):
        adjust(session, move(-1))
    assert balances(session) == []
    assert movements(session) == []
    assert adjust(session, move(2))["quantity"] == 2


def test_missing_references_have_specific_errors(session):
    with pytest.raises(NotFound, match="Item"):
        adjust(session, move(1))
    create_item(session, "BOX", "Box")
    with pytest.raises(NotFound, match="Warehouse"):
        adjust(session, move(1))
    assert session.scalars(select(Stock)).all() == []
    assert session.scalars(select(Movement)).all() == []


def test_zero_move_never_creates_an_audit_entry(session):
    seed(session)
    with pytest.raises(Conflict, match="must change"):
        adjust(session, move(0))
    assert movements(session) == []


def test_warehouse_balances_are_independent(session):
    seed(session)
    create_warehouse(session, "SOUTH", "South")
    adjust(session, move(8))
    adjust(session, move(3, warehouse_id=2))
    adjust(session, move(-2))
    assert [(row.warehouse_id, row.quantity) for row in balances(session)] == [(1, 6), (2, 3)]
    assert [row.quantity for row in balances(session, 2)] == [3]
    assert balances(session, 999) == []


def test_item_balances_are_independent(session):
    seed(session)
    create_item(session, "BAG", "Bag")
    adjust(session, move(8))
    adjust(session, move(3, item_id=2))
    assert [(row.item_id, row.quantity) for row in balances(session)] == [(1, 8), (2, 3)]


def test_large_allowed_adjustments_remain_exact(session):
    seed(session)
    for delta in [100000, 100000, -100000]:
        result = adjust(session, move(delta))
    assert result["quantity"] == 100000
    assert sum(row.delta for row in movements(session)) == result["quantity"]


def test_balance_order_is_warehouse_then_item(session):
    seed(session)
    create_item(session, "BAG", "Bag")
    create_warehouse(session, "SOUTH", "South")
    for item_id, warehouse_id in [(2, 2), (1, 2), (2, 1), (1, 1)]:
        adjust(session, move(1, item_id, warehouse_id))
    assert [(row.warehouse_id, row.item_id) for row in balances(session)] == [
        (1, 1),
        (1, 2),
        (2, 1),
        (2, 2),
    ]


def test_catalog_primary_keys_do_not_depend_on_sku_sort(session):
    create_item(session, "Z", "Last alphabetically")
    create_item(session, "A", "First alphabetically")
    assert [row.sku for row in all_items(session)] == ["Z", "A"]


def test_foreign_keys_reject_orphan_stock(session):
    from sqlalchemy.exc import IntegrityError

    session.add(Stock(item_id=999, warehouse_id=999, quantity=1))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()
    assert balances(session) == []


def test_database_constraint_rejects_negative_stock(session):
    from sqlalchemy.exc import IntegrityError

    seed(session)
    session.add(Stock(item_id=1, warehouse_id=1, quantity=-1))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()
    assert balances(session) == []


def test_stock_balance_pair_is_unique(session):
    from sqlalchemy.exc import IntegrityError

    seed(session)
    adjust(session, move(1))
    session.add(Stock(item_id=1, warehouse_id=1, quantity=2))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()
    assert balances(session)[0].quantity == 1


def test_audit_timestamp_and_reason_are_persisted(session):
    seed(session)
    adjust(session, move(1))
    row = movements(session)[0]
    assert row.reason == "Fixture count"
    assert row.created_at.year >= 2026
    assert row.item_id == 1
    assert row.warehouse_id == 1


def test_independent_session_sees_committed_move(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'fixture.db'}")
    Base.metadata.create_all(engine)
    factory = make_sessions(engine)
    with factory() as writer:
        seed(writer)
        adjust(writer, move(12))
    with factory() as reader:
        assert balances(reader)[0].quantity == 12
        assert len(movements(reader)) == 1
    engine.dispose()
