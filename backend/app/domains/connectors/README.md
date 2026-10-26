# connectors

**Built (M1):** BE-009. A connector interface (`base.py`) and the demonstration connector
(`demo.py`), which serves the synthetic files in `demo-data/`. Status: Built, awaiting owner
checkpoint.

## How a connector works

A connector only **reads** from an external system and returns CSV in the canonical
import-template columns (`/api/ingestion/templates/{record_type}.csv`). `service.run_sync()` feeds
each record type, in dependency order, through the normal ingestion path: profile, then
`commit_batch`. Connector data therefore gets the same validation, idempotent upsert (GR-11), audit
and import history as a manual upload, and assurance logic never knows where data came from.

```python
class Connector(Protocol):
    key: str          # stored on data_source.connector_key
    is_demo: bool     # demo connectors are labelled DEMO everywhere (GR-14)
    def info(self) -> ConnectorInfo
    def validate_config(self, config: dict) -> dict              # raise ConnectorError on bad config
    def available(self, config: dict, stage: str) -> list[str]   # record types it can deliver
    def fetch(self, config: dict, stage: str, record_type: str) -> tuple[str, bytes]
```

## Adding a real connector (e.g. Xero, QuickBooks, NetSuite, Stripe)

1. Implement the protocol in a new module here. Map the source system's fields to the template
   columns inside `fetch`, and keep every source system's id as the record id so re-syncs stay
   idempotent.
2. Read credentials only from environment or secrets configuration, never from `config` stored in
   the database (GR-15).
3. Register it in `service.CONNECTORS`.
4. Add a test like `tests/test_connectors.py`.
5. Activation needs the vendor's sandbox credentials, which haven't been provided yet (decision 0001
   open items).

Connectors never write back. There is no outbound path (GR-01).

## API
- `GET /api/connectors`: available connectors and their options
- `POST /api/data-sources/connector`: `{name, connector_key, config}`
- `POST /api/data-sources/{id}/sync`: `{stage}` → `connector_sync` job

## Scope
The connector interface and the labelled demonstration connector.

## Task IDs
BE-009

Read each task's exact Acceptance Criteria in `docs/jadassure-task-board.csv` before implementing. Don't infer them from this README.
