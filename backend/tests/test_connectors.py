"""BE-009: connector interface and labelled demonstration connector (FR-09, GR-14, GR-11)."""

from sqlalchemy import func, select

from app.core import jobs
from app.domains.connectors.service import CONNECTORS
from app.domains.contracts.models import CommercialTerm
from app.domains.ingestion.models import InvoiceLine
from tests.factories import add_user, signup


def _demo_source(client, admin, dataset="cirrus-cloud"):
    res = client.post("/api/data-sources/connector", headers=admin.headers,
                      json={"name": "Demo connector", "connector_key": "demo", "config": {"dataset": dataset}})
    assert res.status_code == 201, res.text
    return res.json()


def test_connector_catalogue_marks_demo(client):
    admin = signup(client)
    catalogue = client.get("/api/connectors", headers=admin.headers).json()
    demo = next(c for c in catalogue if c["key"] == "demo")
    assert demo["is_demo"] is True and "DEMO" in demo["label"]
    assert {"northwind-advisory", "cirrus-cloud", "ridgeline-supply"} <= set(demo["options"]["dataset"])


def test_every_connector_satisfies_the_interface():
    for connector in CONNECTORS.values():
        for method in ("info", "validate_config", "available", "fetch"):
            assert callable(getattr(connector, method))


def test_sync_loads_through_ingestion_and_is_idempotent(client, session):
    admin = signup(client)
    source = _demo_source(client, admin)
    assert source["is_demo"] is True and source["kind"] == "connector"

    res = client.post(f"/api/data-sources/{source['id']}/sync", headers=admin.headers, json={"stage": "baseline"})
    assert res.status_code == 202 and res.json()["is_demo"] is True
    jobs.drain()

    imports = client.get(f"/api/imports?data_source_id={source['id']}", headers=admin.headers).json()
    assert {i["status"] for i in imports} == {"succeeded"}
    assert all(i["is_demo"] for i in imports)
    assert sum(i["counts"]["rejected"] for i in imports) == 0
    by_type = {i["record_type"]: i["counts"]["inserted"] for i in imports}
    assert by_type["invoice_line"] == 18 and by_type["commercial_term"] == 5
    assert session.scalar(select(func.count()).select_from(CommercialTerm).where(
        CommercialTerm.status == "confirmed")) == 5

    client.post(f"/api/data-sources/{source['id']}/sync", headers=admin.headers, json={"stage": "baseline"})
    jobs.drain()
    second = client.get(f"/api/imports?data_source_id={source['id']}", headers=admin.headers).json()[: len(imports)]
    assert sum(i["counts"]["inserted"] + i["counts"]["updated"] for i in second) == 0
    assert session.scalar(select(func.count()).select_from(InvoiceLine)) == 18


def test_bad_config_and_stage_are_rejected(client):
    admin = signup(client)
    res = client.post("/api/data-sources/connector", headers=admin.headers,
                      json={"name": "x", "connector_key": "demo", "config": {"dataset": "../../etc"}})
    assert res.status_code == 422
    res = client.post("/api/data-sources/connector", headers=admin.headers,
                      json={"name": "x", "connector_key": "netsuite", "config": {}})
    assert res.status_code == 422
    source = _demo_source(client, admin)
    assert client.post(f"/api/data-sources/{source['id']}/sync", headers=admin.headers,
                       json={"stage": "contracts"}).status_code == 422
    assert client.post(f"/api/data-sources/{source['id']}/sync", headers=admin.headers,
                       json={"stage": "../x"}).status_code == 422


def test_csv_sources_cannot_be_synced_and_sync_is_scoped(client):
    admin = signup(client)
    csv_source = client.post("/api/data-sources", headers=admin.headers, json={"name": "Manual"}).json()
    assert client.post(f"/api/data-sources/{csv_source['id']}/sync", headers=admin.headers,
                       json={"stage": "baseline"}).status_code == 409
    source = _demo_source(client, admin)
    other = signup(client)
    assert client.post(f"/api/data-sources/{source['id']}/sync", headers=other.headers,
                       json={"stage": "baseline"}).status_code == 404
    analyst = add_user(client, admin, "analyst")
    assert client.get("/api/connectors", headers=analyst.headers).status_code == 403
