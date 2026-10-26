"""Stock adjustment and audit entry commit as a single transaction.

SQLite serializes writes. Conditional updates guard against lost decrements on
existing balances; this example intentionally has no cross-process retry policy.
"""

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from .errors import Conflict, NotFound
from .models import Item, Movement, Stock, Warehouse


def adjust(session, data):
    if session.get(Item, data.item_id) is None:
        raise NotFound("Item not found")
    if session.get(Warehouse, data.warehouse_id) is None:
        raise NotFound("Warehouse not found")
    if data.delta == 0:
        raise Conflict("A movement must change stock")
    query = select(Stock).where(
        Stock.item_id == data.item_id, Stock.warehouse_id == data.warehouse_id
    )
    row = session.scalar(query)
    try:
        if row is None:
            if data.delta < 0:
                raise Conflict("Insufficient stock")
            row = Stock(item_id=data.item_id, warehouse_id=data.warehouse_id, quantity=data.delta)
            session.add(row)
        else:
            result = session.execute(
                update(Stock)
                .where(Stock.id == row.id, Stock.quantity + data.delta >= 0)
                .values(quantity=Stock.quantity + data.delta)
                .execution_options(synchronize_session=False)
            )
            if result.rowcount != 1:
                raise Conflict("Insufficient stock")
            session.expire(row)
        movement = Movement(
            item_id=data.item_id,
            warehouse_id=data.warehouse_id,
            delta=data.delta,
            reason=data.reason,
        )
        session.add(movement)
        session.commit()
        session.refresh(row)
        return {"id": movement.id, "quantity": row.quantity}
    except IntegrityError as exc:
        session.rollback()
        raise Conflict("Concurrent stock update; retry request") from exc
    except Conflict:
        session.rollback()
        raise


def balances(session, warehouse_id: int | None = None):
    query = select(Stock).order_by(Stock.warehouse_id, Stock.item_id)
    if warehouse_id is not None:
        query = query.where(Stock.warehouse_id == warehouse_id)
    return session.scalars(query).all()


def movements(session):
    return session.scalars(select(Movement).order_by(Movement.id)).all()
