"""Request-level regression tests using a fresh in-memory SQLite per test."""

import pytest
from fastapi.testclient import TestClient

from inventory.app import create_app


@pytest.fixture
def client():
    with TestClient(create_app("sqlite://")) as client:
        yield client


def seed(client):
    item = client.post("/items", json={"sku": "BOX-1", "name": "Sample box"}).json()
    warehouse = client.post("/warehouses", json={"code": "NORTH", "name": "North"}).json()
    return {"item_id": item["id"], "warehouse_id": warehouse["id"], "reason": "Count"}


def test_health_and_empty_catalog(client):
    assert client.get("/health").json() == {"status": "ok"}
    for path in ["/items", "/warehouses", "/stock", "/v1/items"]:
        assert client.get(path).json() == []


def test_catalog_unique_and_sorted(client):
    seed(client)
    assert client.post("/items", json={"sku": "BOX-1", "name": "Other"}).status_code == 409
    assert client.post("/warehouses", json={"code": "NORTH", "name": "Other"}).status_code == 409
    assert client.get("/items").json()[0]["name"] == "Sample box"
    assert client.get("/v1/items").json() == client.get("/items").json()
    assert client.get("/warehouses").json()[0]["code"] == "NORTH"


def test_moves_are_atomic_and_filterable(client):
    data = seed(client)
    first = client.post("/moves", json={**data, "delta": 10})
    assert first.status_code == 201
    assert first.json() == {"id": 1, "quantity": 10}
    assert client.post("/moves", json={**data, "delta": -3}).json()["quantity"] == 7
    assert client.post("/moves", json={**data, "delta": -8}).status_code == 409
    assert client.get("/stock").json() == [{"item_id": 1, "warehouse_id": 1, "quantity": 7}]
    assert client.get("/stock?warehouse_id=1").json()[0]["quantity"] == 7
    assert client.get("/stock?warehouse_id=2").json() == []
    assert client.post("/moves", json={**data, "delta": -7}).json() == {"id": 3, "quantity": 0}


def test_move_rejections(client):
    data = seed(client)
    assert client.post("/moves", json={**data, "delta": 0}).status_code == 409
    assert client.post("/moves", json={**data, "delta": -1}).status_code == 409
    assert client.post("/moves", json={**data, "item_id": 99, "delta": 1}).status_code == 404
    assert client.post("/moves", json={**data, "warehouse_id": 99, "delta": 1}).status_code == 404
    assert client.get("/stock").json() == []


@pytest.mark.parametrize(
    "body",
    [
        {"sku": "bad space", "name": "A"},
        {"sku": "A", "name": " "},
        {"sku": "A" * 41, "name": "A"},
        {},
    ],
)
def test_invalid_items(client, body):
    assert client.post("/items", json=body).status_code == 422
    assert client.get("/items").json() == []


@pytest.mark.parametrize("delta", [1.5, "2", True, 100001, -100001])
def test_strict_quantity_validation(client, delta):
    data = seed(client)
    assert client.post("/moves", json={**data, "delta": delta}).status_code == 422


def test_invalid_warehouse_and_reason(client):
    assert client.post("/warehouses", json={"code": "bad", "name": "A"}).status_code == 422
    data = seed(client)
    assert client.post("/moves", json={**data, "delta": 1, "reason": " "}).status_code == 422


def test_stock_audit_matches_quantity():
    from sqlalchemy import select

    from inventory.database import Base, make_engine, make_sessions
    from inventory.models import Item, Movement, Warehouse
    from inventory.schemas import MoveCreate
    from inventory.stock import adjust, movements

    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    with make_sessions(engine)() as session:
        session.add_all([Item(sku="A", name="A"), Warehouse(code="N", name="N")])
        session.commit()
        for delta in [4, -1, 2]:
            adjust(session, MoveCreate(item_id=1, warehouse_id=1, delta=delta, reason="Count"))
        assert [m.delta for m in movements(session)] == [4, -1, 2]
        assert len(session.scalars(select(Movement)).all()) == 3
    engine.dispose()
