# Sample Inventory

A local warehouse catalog and immutable stock ledger. Python 3.12, FastAPI,
SQLAlchemy 2 and SQLite. Fake data only; no hosted services.

## Run

```sh
python -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn inventory.app:create_app --factory
```

Open `/docs` for the API schema. The default database is `inventory.db` in the
working directory. `create_app("sqlite://")` creates isolated in-memory storage.
Schema creation occurs at startup; this sample does not ship a migration tool.

## API

- POST `/items`: `{ "sku": "BOX-1", "name": "Sample box" }`
- GET `/items`: ID-ordered list of items; all records are returned.
- POST `/warehouses`: `{ "code": "NORTH", "name": "North warehouse" }`
- GET `/warehouses`: ID-ordered list.
- POST `/moves`: `{ "item_id": 1, "warehouse_id": 1, "delta": 10, "reason": "Initial count" }`
- GET `/stock?warehouse_id=1`: balances, optionally filtered by warehouse.
- GET `/v1/items`: deprecated compatibility endpoint still used by terminal clients.
- GET `/health`: local process health.

A move cannot produce negative stock. Missing references return 404; duplicates,
zero adjustments and insufficient stock return 409. Pydantic validation returns
422. Move audit and balance update share a transaction. SQLite is intended for
one small local service; concurrent creation conflicts return retryable 409.
No authentication is included: bind to loopback only for demonstrations.

## Quality

`ruff check .` and `pytest` match CI. Tests use isolated in-memory databases and
exercise HTTP validation, persistence, filtering, audit order and rollback.
Coverage must reach 75%. The app factory deliberately repeats session scopes:
TODO consider a shared dependency when additional route groups are introduced.
MIT licensed.

CI verification: documentation-only check.
