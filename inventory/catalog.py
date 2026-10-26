"""Catalog access; callers own the request-scoped session."""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from .errors import Conflict
from .models import Item, Warehouse


def create_item(session, sku: str, name: str):
    row = Item(sku=sku, name=name)
    session.add(row)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise Conflict("SKU already exists") from exc
    return row


def items(session):
    return session.scalars(select(Item).order_by(Item.id)).all()


def create_warehouse(session, code: str, name: str):
    row = Warehouse(code=code, name=name)
    session.add(row)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise Conflict("Warehouse code already exists") from exc
    return row


def warehouses(session):
    return session.scalars(select(Warehouse).order_by(Warehouse.id)).all()
