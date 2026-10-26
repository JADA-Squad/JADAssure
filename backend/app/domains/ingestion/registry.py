"""Field registry: the single definition of every importable field (BE-005, FR-04).

Templates, profiling, validation and the commit upsert are all driven from this registry, so a
field is defined exactly once. The first field of each record type is its source record id.
"""

from dataclasses import dataclass, field
from typing import Literal

FieldType = Literal["id", "str", "date", "decimal", "int", "currency", "enum", "ref"]


@dataclass(frozen=True)
class FieldSpec:
    name: str  # canonical CSV column
    type: FieldType
    required: bool = False
    description: str = ""
    attr: str | None = None  # model attribute; defaults to `name`
    ref: str | None = None  # record type referenced by source id (type == "ref")
    choices: tuple[str, ...] = ()
    synonyms: tuple[str, ...] = ()
    max_length: int = 200

    @property
    def model_attr(self) -> str:
        return self.attr or self.name


@dataclass(frozen=True)
class RecordSpec:
    record_type: str
    label: str
    fields: tuple[FieldSpec, ...]
    depends_on: tuple[str, ...] = field(default=())

    @property
    def id_field(self) -> FieldSpec:
        return self.fields[0]

    def get(self, name: str) -> FieldSpec | None:
        return next((f for f in self.fields if f.name == name), None)


def _id(name: str, label: str) -> FieldSpec:
    return FieldSpec(name, "id", True, f"Unique {label} identifier in the source system")


def _ref(name: str, ref: str, required: bool = True, description: str = "", attr: str | None = None,
         synonyms: tuple[str, ...] = ()) -> FieldSpec:
    return FieldSpec(
        name, "ref", required, description or f"{ref.replace('_', ' ')} id from the source system", attr=attr, ref=ref,
        synonyms=synonyms,
    )


CURRENCY = FieldSpec("currency", "currency", True, "ISO 4217 code, e.g. USD", synonyms=("ccy", "curr"))

RECORDS: dict[str, RecordSpec] = {
    spec.record_type: spec
    for spec in (
        RecordSpec("customer", "Customers", (
            _id("customer_id", "customer"),
            FieldSpec("name", "str", True, "Customer name", synonyms=("customer_name", "account_name")),
            CURRENCY,
        )),
        RecordSpec("agreement", "Agreements", (
            _id("agreement_id", "agreement"),
            _ref("customer_id", "customer"),
            FieldSpec("title", "str", True, "Agreement title", synonyms=("name", "contract_name")),
            FieldSpec("start_date", "date", True, "YYYY-MM-DD"),
            FieldSpec("end_date", "date", False, "YYYY-MM-DD; blank if open-ended"),
            FieldSpec("billing_frequency", "enum", True, "How often billing happens",
                      choices=("monthly", "quarterly", "annual", "per_event", "milestone")),
            CURRENCY,
        ), depends_on=("customer",)),
        RecordSpec("agreement_version", "Agreement versions (amendments)", (
            _id("version_id", "agreement version"),
            _ref("agreement_id", "agreement"),
            FieldSpec("version_no", "int", True, "1 for the original agreement, 2+ for amendments"),
            FieldSpec("effective_from", "date", True, "YYYY-MM-DD"),
            FieldSpec("effective_to", "date", False, "YYYY-MM-DD; blank if still in effect"),
            FieldSpec("reason", "str", False, "Why this version exists", max_length=500),
        ), depends_on=("agreement",)),
        RecordSpec("commercial_term", "Commercial terms", (
            _id("term_id", "term"),
            _ref("version_id", "agreement_version", description="Agreement version this term belongs to",
                 attr="agreement_version_id"),
            FieldSpec("item_code", "str", False, "Product/service code; blank for agreement-wide terms",
                      synonyms=("sku", "product_code", "service_code")),
            FieldSpec("term_type", "enum", True, "Kind of term",
                      choices=("rate", "discount", "escalation", "credit_policy", "minimum")),
            FieldSpec("value", "decimal", True,
                      "rate: unit price; discount: max %; escalation: % or new rate; credit_policy: approval threshold"),
            FieldSpec("unit", "str", False, "e.g. hour, seat, unit, pct, rate"),
            FieldSpec("currency", "currency", False, "ISO 4217 code for money values"),
            FieldSpec("effective_from", "date", True, "YYYY-MM-DD"),
            FieldSpec("effective_to", "date", False, "YYYY-MM-DD; blank if open-ended"),
            FieldSpec("approval_ref", "str", False, "Reference of the approval behind this term"),
            FieldSpec("max_value", "decimal", False, "credit_policy: maximum credit allowed", attr="params.max_value"),
        ), depends_on=("agreement_version",)),
        RecordSpec("billable_event", "Billable events (deliveries)", (
            _id("event_id", "billable event"),
            _ref("customer_id", "customer"),
            _ref("agreement_id", "agreement", required=False, synonyms=("contract", "contract_id")),
            FieldSpec("item_code", "str", True, "Product/service code", synonyms=("sku", "product_code", "service_code")),
            FieldSpec("quantity", "decimal", True, "Delivered quantity", synonyms=("qty", "hours", "units")),
            FieldSpec("unit", "str", False, "e.g. hour, seat, unit"),
            FieldSpec("service_date", "date", True, "Date the work/usage/delivery happened",
                      synonyms=("delivery_date", "ship_date", "work_date")),
            FieldSpec("billing_date", "date", False, "Date this event should have been billed by",
                      synonyms=("bill_by", "bill_date")),
            CURRENCY,
        ), depends_on=("customer", "agreement")),
        RecordSpec("invoice", "Invoices", (
            _id("invoice_id", "invoice"),
            _ref("customer_id", "customer"),
            FieldSpec("number", "str", True, "Invoice number", synonyms=("invoice_number", "invoice_no")),
            FieldSpec("invoice_date", "date", True, "YYYY-MM-DD", synonyms=("date",)),
            CURRENCY,
            FieldSpec("status", "str", False, "Status in the billing system"),
            FieldSpec("correction_reference", "str", False, "JADAssure correction reference, if this invoice corrects a finding"),
        ), depends_on=("customer",)),
        RecordSpec("invoice_line", "Invoice lines", (
            _id("line_id", "invoice line"),
            _ref("invoice_id", "invoice"),
            _ref("agreement_id", "agreement", required=False),
            FieldSpec("item_code", "str", True, "Product/service code", synonyms=("sku", "product_code", "service_code")),
            FieldSpec("quantity", "decimal", True, "Billed quantity", synonyms=("qty",)),
            FieldSpec("unit_price", "decimal", True, "List unit price before discount", synonyms=("price", "rate")),
            FieldSpec("discount_pct", "decimal", False, "Discount percent applied, e.g. 10 for 10%", synonyms=("discount",)),
            FieldSpec("net_amount", "decimal", True, "Line amount excluding tax", synonyms=("amount", "net")),
            FieldSpec("tax_amount", "decimal", False, "Tax on the line", synonyms=("tax", "vat")),
            FieldSpec("service_period_start", "date", False, "First day of the service period billed"),
            FieldSpec("service_period_end", "date", False, "Last day of the service period billed"),
        ), depends_on=("invoice", "agreement")),
        RecordSpec("credit", "Credits and adjustments", (
            _id("credit_id", "credit"),
            _ref("customer_id", "customer"),
            _ref("invoice_id", "invoice", required=False),
            FieldSpec("amount", "decimal", True, "Credit amount (positive)"),
            CURRENCY,
            FieldSpec("reason_code", "str", False, "Why the credit was issued"),
            FieldSpec("approval_ref", "str", False, "Reference of the approval behind this credit"),
            FieldSpec("credit_date", "date", True, "YYYY-MM-DD", synonyms=("date",)),
        ), depends_on=("customer", "invoice")),
        RecordSpec("payment", "Payments", (
            _id("payment_id", "payment"),
            _ref("customer_id", "customer"),
            FieldSpec("amount", "decimal", True, "Amount received"),
            CURRENCY,
            FieldSpec("payment_date", "date", True, "YYYY-MM-DD", synonyms=("date",)),
        ), depends_on=("customer",)),
        RecordSpec("payment_allocation", "Payment allocations", (
            _id("allocation_id", "payment allocation"),
            _ref("payment_id", "payment"),
            _ref("invoice_id", "invoice"),
            FieldSpec("amount", "decimal", True, "Amount of the payment applied to the invoice"),
        ), depends_on=("payment", "invoice")),
        RecordSpec("cost_record", "Cost records (optional)", (
            _id("cost_id", "cost record"),
            FieldSpec("item_code", "str", True, "Product/service code", synonyms=("sku", "product_code")),
            FieldSpec("unit_cost", "decimal", True, "Cost per unit", synonyms=("cost",)),
            CURRENCY,
            FieldSpec("effective_from", "date", True, "YYYY-MM-DD"),
            FieldSpec("effective_to", "date", False, "YYYY-MM-DD; blank if open-ended"),
        )),
    )
}

# Dependency order for multi-file loads (design §3.3).
LOAD_ORDER: tuple[str, ...] = (
    "customer", "agreement", "agreement_version", "commercial_term", "billable_event", "invoice",
    "invoice_line", "credit", "payment", "payment_allocation", "cost_record",
)
assert set(LOAD_ORDER) == set(RECORDS)


def template_csv(record_type: str) -> str:
    """Header row only. No example row, so a template can't be imported as data by mistake."""
    return ",".join(f.name for f in RECORDS[record_type].fields) + "\r\n"
