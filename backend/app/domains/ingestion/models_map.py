"""Record type → canonical model class."""

from app.domains.contracts.models import Agreement, AgreementVersion, CommercialTerm
from app.domains.ingestion.models import (
    BillableEvent,
    CostRecord,
    Credit,
    Customer,
    Invoice,
    InvoiceLine,
    Payment,
    PaymentAllocation,
)

MODELS = {
    "customer": Customer,
    "agreement": Agreement,
    "agreement_version": AgreementVersion,
    "commercial_term": CommercialTerm,
    "billable_event": BillableEvent,
    "invoice": Invoice,
    "invoice_line": InvoiceLine,
    "credit": Credit,
    "payment": Payment,
    "payment_allocation": PaymentAllocation,
    "cost_record": CostRecord,
}
