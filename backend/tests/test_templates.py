"""BE-005: a template per record type, generated from the same registry used for validation (FR-04)."""

import csv
import io

import pytest
from sqlalchemy import inspect

from app.core import db
from app.domains.ingestion.models_map import MODELS
from app.domains.ingestion.registry import LOAD_ORDER, RECORDS
from tests.factories import add_user, signup

# requirements §5 record types (cost record is optional but still has a template)
REQUIRED_TYPES = {
    "customer", "agreement", "agreement_version", "commercial_term", "billable_event", "invoice", "invoice_line",
    "credit", "payment", "payment_allocation", "cost_record",
}


def test_registry_covers_every_record_type():
    assert set(RECORDS) == REQUIRED_TYPES == set(LOAD_ORDER) == set(MODELS)


@pytest.mark.parametrize("record_type", sorted(REQUIRED_TYPES))
def test_template_header_matches_registry(client, record_type):
    admin = signup(client)
    res = client.get(f"/api/ingestion/templates/{record_type}.csv", headers=admin.headers)
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/csv")
    rows = list(csv.reader(io.StringIO(res.text)))
    assert rows == [[f.name for f in RECORDS[record_type].fields]]


@pytest.mark.parametrize("record_type", sorted(REQUIRED_TYPES))
def test_registry_fields_map_to_real_model_columns(record_type):
    columns = {c["name"] for c in inspect(db.get_engine()).get_columns(MODELS[record_type].__tablename__)}
    spec = RECORDS[record_type]
    for f in spec.fields[1:]:
        if f.model_attr.startswith("params."):
            assert "params" in columns
        else:
            assert f.model_attr in columns, f"{record_type}.{f.name}"


def test_references_point_at_known_record_types_loaded_earlier():
    for record_type, spec in RECORDS.items():
        for f in spec.fields:
            if f.type == "ref":
                assert f.ref in RECORDS
                assert LOAD_ORDER.index(f.ref) < LOAD_ORDER.index(record_type), f"{record_type}.{f.name}"


def test_unknown_record_type_is_rejected(client):
    admin = signup(client)
    assert client.get("/api/ingestion/templates/secrets.csv", headers=admin.headers).status_code == 422


def test_templates_require_manage_data(client):
    admin = signup(client)
    analyst = add_user(client, admin, "analyst")
    assert client.get("/api/ingestion/templates/customer.csv", headers=analyst.headers).status_code == 403
    assert client.get("/api/ingestion/record-types", headers=analyst.headers).status_code == 403
