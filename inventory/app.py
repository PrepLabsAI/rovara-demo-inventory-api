"""Application factory used by both uvicorn and isolated HTTP tests."""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from . import catalog, stock
from .database import Base, make_engine, make_sessions
from .errors import Conflict, NotFound
from .schemas import (
    ItemCreate,
    ItemView,
    MoveCreate,
    MoveView,
    StockView,
    WarehouseCreate,
    WarehouseView,
)


def create_app(url: str = "sqlite:///inventory.db") -> FastAPI:
    engine = make_engine(url)
    sessions = make_sessions(engine)

    @asynccontextmanager
    async def lifespan(_app):
        Base.metadata.create_all(engine)
        yield
        engine.dispose()

    app = FastAPI(title="Sample Inventory", lifespan=lifespan)

    @app.exception_handler(Conflict)
    async def conflict(_request: Request, exc: Conflict):
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.exception_handler(NotFound)
    async def missing(_request: Request, exc: NotFound):
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.post("/items", response_model=ItemView, status_code=201)
    def add_item(body: ItemCreate):
        with sessions() as session:
            return catalog.create_item(session, body.sku, body.name)

    @app.get("/items", response_model=list[ItemView])
    def list_items():
        with sessions() as session:
            return catalog.items(session)

    @app.post("/warehouses", response_model=WarehouseView, status_code=201)
    def add_warehouse(body: WarehouseCreate):
        with sessions() as session:
            return catalog.create_warehouse(session, body.code, body.name)

    @app.get("/warehouses", response_model=list[WarehouseView])
    def list_warehouses():
        with sessions() as session:
            return catalog.warehouses(session)

    @app.post("/moves", response_model=MoveView, status_code=201)
    def move(body: MoveCreate):
        with sessions() as session:
            return stock.adjust(session, body)

    @app.get("/stock", response_model=list[StockView])
    def list_stock(warehouse_id: int | None = None):
        with sessions() as session:
            return stock.balances(session, warehouse_id)

    @app.get("/v1/items", response_model=list[ItemView], deprecated=True)
    def legacy_items():
        with sessions() as session:
            return catalog.items(session)

    return app
