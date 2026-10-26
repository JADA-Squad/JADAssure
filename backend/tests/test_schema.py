"""BE-001: the migration creates every design §3.2 entity with decimal money and source keys."""

from decimal import Decimal

import pytest
from sqlalchemy import inspect

from app.core import db
from app.core.money import to_money

ENTITIES = {
    "organization", "app_user", "data_source", "import_batch", "customer", "agreement", "agreement_version",
    "commercial_term", "billable_event", "invoice", "invoice_line", "credit", "payment", "payment_allocation",
    "cost_record", "document", "rule", "rule_version", "check_run", "finding", "investigation_event", "approval",
    "correction", "recovery_event", "job", "audit_event",
}
SOURCE_BACKED = {
    "customer", "agreement", "agreement_version", "commercial_term", "billable_event", "invoice", "invoice_line",
    "credit", "payment", "payment_allocation", "cost_record",
}
MONEY_COLUMNS = {
    ("invoice_line", "net_amount"), ("invoice_line", "tax_amount"), ("invoice_line", "unit_price"),
    ("credit", "amount"), ("payment", "amount"), ("payment_allocation", "amount"), ("finding", "value"),
    ("correction", "amount"), ("recovery_event", "amount"), ("cost_record", "unit_cost"),
    ("commercial_term", "value"), ("billable_event", "quantity"),
}


@pytest.fixture(scope="module")
def inspector():
    return inspect(db.get_engine())


def test_every_entity_exists(inspector):
    assert ENTITIES <= set(inspector.get_table_names())


@pytest.mark.parametrize("table,column", sorted(MONEY_COLUMNS))
def test_money_columns_are_numeric(inspector, table, column):
    col = next(c for c in inspector.get_columns(table) if c["name"] == column)
    assert col["type"].__class__.__name__ == "NUMERIC"


@pytest.mark.parametrize("table", sorted(SOURCE_BACKED))
def test_source_backed_tables_have_unique_source_key(inspector, table):
    uniques = {tuple(u["column_names"]) for u in inspector.get_unique_constraints(table)}
    assert ("org_id", "data_source_id", "source_record_id") in uniques
    cols = {c["name"] for c in inspector.get_columns(table)}
    assert {"source_payload", "source_hash", "import_id"} <= cols


def test_every_money_table_has_currency(inspector):
    for table in ("invoice", "credit", "payment", "finding", "correction", "cost_record", "billable_event"):
        assert "currency" in {c["name"] for c in inspector.get_columns(table)}, table


def test_to_money_rejects_float_and_rounds_half_even():
    assert to_money(Decimal("1.00005")) == Decimal("1.0000")
    assert to_money(Decimal("1.00015")) == Decimal("1.0002")
    with pytest.raises(TypeError):
        to_money(1.5)  # type: ignore[arg-type]
