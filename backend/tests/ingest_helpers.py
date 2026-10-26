"""Helpers for driving imports through the API, as the UI does."""

from fastapi.testclient import TestClient

from app.core import jobs
from tests.factories import Actor


def create_source(client: TestClient, admin: Actor, name: str = "ERP export") -> str:
    res = client.post("/api/data-sources", headers=admin.headers, json={"name": name})
    assert res.status_code == 201, res.text
    return res.json()["id"]


def upload(client: TestClient, admin: Actor, source_id: str, record_type: str, csv_text: str,
           filename: str = "data.csv") -> dict:
    res = client.post(
        f"/api/data-sources/{source_id}/imports",
        headers=admin.headers,
        data={"record_type": record_type},
        files={"file": (filename, csv_text.encode("utf-8"), "text/csv")},
    )
    assert res.status_code == 201, res.text
    return res.json()


def commit(client: TestClient, admin: Actor, import_id: str) -> dict:
    res = client.post(f"/api/imports/{import_id}/commit", headers=admin.headers)
    assert res.status_code == 200, res.text
    jobs.drain()
    return client.get(f"/api/imports/{import_id}", headers=admin.headers).json()


def load(client: TestClient, admin: Actor, source_id: str, record_type: str, csv_text: str) -> dict:
    """Upload with the suggested mapping and commit; asserts the import succeeded."""
    batch = commit(client, admin, upload(client, admin, source_id, record_type, csv_text)["id"])
    assert batch["status"] == "succeeded", batch
    return batch


CUSTOMERS = "customer_id,name,currency\nC1,Halcyon Retail,USD\nC2,Bluefin Logistics,usd\n"
