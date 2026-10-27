"""HTTP schemas keep invalid quantities outside the transaction boundary."""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
Sku = Annotated[str, StringConstraints(pattern=r"^[A-Z0-9-]{1,40}$")]
Code = Annotated[str, StringConstraints(pattern=r"^[A-Z0-9-]{1,20}$")]


class ItemCreate(BaseModel):
    sku: Sku
    name: Name


class ItemView(ItemCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    active: bool


class ItemPage(BaseModel):
    items: list[ItemView]
    total: int
    limit: int
    offset: int


class WarehouseCreate(BaseModel):
    code: Code
    name: Name


class WarehouseView(WarehouseCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int


class MoveCreate(BaseModel):
    item_id: int = Field(gt=0)
    warehouse_id: int = Field(gt=0)
    delta: int = Field(strict=True, ge=-100000, le=100000)
    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


class StockView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    item_id: int
    warehouse_id: int
    quantity: int


class MoveView(BaseModel):
    id: int
    quantity: int
