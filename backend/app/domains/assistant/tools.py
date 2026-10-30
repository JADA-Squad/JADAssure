"""The assistant's tools (BE-034, decision 0009).

Each tool needs a capability, so a user's assistant only gets the tools their role permits (D-2).
Read tools return live data through the same service functions as the screens. Write tools never
change anything here: `prepare` validates and describes the action, and `execute` runs only after
the user confirms it (GR-17), through the existing workflow code with the user's own context.
"""

import json
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from fastapi import HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.tenancy import TenantContext, get_scoped
from app.domains.access.permissions import Cap, has_cap
from app.domains.cases import service as cases
from app.domains.cases import workflow
from app.domains.contracts import extraction
from app.domains.contracts.models import CommercialTerm
from app.domains.contracts.router import _review_rows
from app.domains.contracts.router import list_agreements as _list_agreements
from app.domains.recovery.router import tracker as _tracker
from app.domains.reporting import pricing
from app.domains.reporting import service as reporting
from app.domains.rules import engine
from app.domains.rules.models import ROOT_CAUSES, Finding
from app.domains.rules.runs_router import list_runs as _list_runs

MAX_RESULT_CHARS = 12_000
CHECK_TYPES = ["delivered_not_billed", "incorrect_rate", "expired_discount", "missed_increase", "credit_outside_policy"]
CHECK_LABELS = {"delivered_not_billed": "Delivered not billed", "incorrect_rate": "Incorrect contracted rate",
                "expired_discount": "Expired or unauthorized discount",
                "missed_increase": "Missed contractual increase", "credit_outside_policy": "Credit outside policy"}
STATUSES = ["open", "in_review", "proposed", "approved", "billed", "recovered", "rejected", "closed_no_recovery"]


class ToolError(Exception):
    """Shown to the model as an error result; it can correct itself or explain to the user."""


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    caps: tuple[Cap, ...]  # any one suffices
    properties: dict[str, Any] = field(default_factory=dict)
    required: tuple[str, ...] = ()
    read: Callable[[Session, TenantContext, dict], Any] | None = None
    prepare: Callable[[Session, TenantContext, dict], str] | None = None
    execute: Callable[[Session, TenantContext, dict], str] | None = None

    @property
    def writes(self) -> bool:
        return self.execute is not None

    def allowed(self, role: str) -> bool:
        return any(has_cap(role, c) for c in self.caps)

    def definition(self) -> dict[str, Any]:
        return {"name": self.name, "description": self.description,
                "input_schema": {"type": "object", "properties": self.properties, "required": list(self.required),
                                 "additionalProperties": False}}


# ---------------------------------------------------------------- helpers

def to_json(obj: Any) -> str:
    """Money stays a decimal string (GR-09); long results are cut to keep requests small (D-6)."""
    def default(o: Any) -> Any:
        if isinstance(o, BaseModel):
            return o.model_dump(mode="json")
        if isinstance(o, Decimal | uuid.UUID):
            return str(o)
        if isinstance(o, date | datetime):
            return o.isoformat()
        raise TypeError(type(o).__name__)

    text = json.dumps(obj, default=default, ensure_ascii=False)
    return text if len(text) <= MAX_RESULT_CHARS else text[:MAX_RESULT_CHARS] + " …(truncated; narrow the request)"


def _uuid(args: dict, key: str) -> uuid.UUID:
    try:
        return uuid.UUID(str(args.get(key)))
    except ValueError:
        raise ToolError(f"{key} must be an id returned by another tool") from None


def _text(args: dict, key: str, limit: int, required: bool = True) -> str | None:
    value = (args.get(key) or "").strip()
    if required and not value:
        raise ToolError(f"{key} is required")
    if len(value) > limit:
        raise ToolError(f"{key} must be at most {limit} characters")
    return value or None


def _finding(session: Session, ctx: TenantContext, args: dict) -> Finding:
    try:
        return get_scoped(session, Finding, _uuid(args, "finding_id"), ctx)
    except HTTPException:
        raise ToolError("No such finding in your organization") from None


def _label(f: Finding) -> str:
    customer = ((f.evidence or {}).get("customer") or {}).get("name") or "unknown customer"
    return f"{f.value:,.2f} {f.currency} · {CHECK_LABELS.get(f.check_type, f.check_type)} · {customer}"


def _can(ctx: TenantContext, f: Finding, action: str) -> None:
    if action not in cases.available_actions(ctx, f):
        if action == "approve" and f.proposer_id == ctx.user_id:
            raise ToolError("You proposed this finding, so a different approver must approve it (separation of duties)")
        raise ToolError(f"Can't {action.replace('_', ' ')} this finding while it is {f.status}")


FINDING_ID = {"finding_id": {"type": "string", "description": "Finding id (from list_findings)"}}


# ---------------------------------------------------------------- read tools

def _list_findings(session: Session, ctx: TenantContext, args: dict) -> Any:
    statuses = [s for s in (args.get("statuses") or []) if s in STATUSES] or None
    min_value = None
    if args.get("min_value") not in (None, ""):
        try:
            min_value = Decimal(str(args["min_value"]))
        except ArithmeticError:
            raise ToolError("min_value must be a number") from None
    page = cases.list_findings(
        session, ctx, statuses=statuses, check_type=args.get("check_type") or None,
        customer_id=_uuid(args, "customer_id") if args.get("customer_id") else None, min_value=min_value,
        unassigned=bool(args.get("unassigned")), limit=min(int(args.get("limit") or 25), 50))
    keep = ("id", "check_type", "status", "value", "currency", "confidence", "customer_name", "agreement_title",
            "item_code", "period_start", "period_end", "owner_name", "reason", "age_days")
    return {"total": page.total, "value_by_currency": page.value_by_currency,
            "items": [{k: getattr(i, k) for k in keep} for i in page.items]}


def _get_finding(session: Session, ctx: TenantContext, args: dict) -> Any:
    f = _finding(session, ctx, args)
    return cases.detail(session, ctx, f.id)


def _team(session: Session, ctx: TenantContext, args: dict) -> Any:
    flt = cases.filters(session, ctx)
    return {"your_user_id": str(ctx.user_id), "possible_owners": flt.owners, "customers": flt.customers}


def _outcomes(session: Session, ctx: TenantContext, args: dict) -> Any:
    return reporting.outcomes(session, ctx.org_id)


def _pricing(session: Session, ctx: TenantContext, args: dict) -> Any:
    return pricing.opportunities(session, ctx.org_id)


def _corrections(session: Session, ctx: TenantContext, args: dict) -> Any:
    return _tracker(ctx=ctx, session=session)


def _agreements(session: Session, ctx: TenantContext, args: dict) -> Any:
    return _list_agreements(ctx=ctx, session=session)


def _terms(session: Session, ctx: TenantContext, args: dict) -> Any:
    status_ = args.get("status") if args.get("status") in ("proposed", "confirmed", "rejected") else "proposed"
    return _review_rows(session, ctx, status_=status_)


def _runs(session: Session, ctx: TenantContext, args: dict) -> Any:
    return _list_runs(limit=5, ctx=ctx, session=session)


# ---------------------------------------------------------------- write tools: prepare + execute

def _prep_assign(session, ctx, args):
    f = _finding(session, ctx, args)
    _can(ctx, f, "assign")
    owner = args.get("owner_id")
    if owner:
        _uuid(args, "owner_id")
    who = "yourself" if owner == str(ctx.user_id) else ("nobody (unassign)" if not owner else "the chosen owner")
    return f"Assign finding {_label(f)} to {who}."


def _exec_assign(session, ctx, p):
    owner = uuid.UUID(p["owner_id"]) if p.get("owner_id") else None
    workflow.assign(session, ctx, uuid.UUID(p["finding_id"]), owner)
    return "Assigned."


def _prep_comment(session, ctx, args):
    f = _finding(session, ctx, args)
    _can(ctx, f, "comment")
    body = _text(args, "text", 4000)
    return f"Add a comment to finding {_label(f)}: “{body}”"


def _exec_comment(session, ctx, p):
    cases.add_comment(session, ctx, uuid.UUID(p["finding_id"]), p["text"])
    return "Comment added."


def _prep_propose(session, ctx, args):
    f = _finding(session, ctx, args)
    if f.status not in ("open", "in_review"):
        raise ToolError(f"Can't propose a finding that is {f.status}")
    if not has_cap(ctx.role, Cap.PROPOSE_REJECT):
        raise ToolError("Your role can't propose findings")
    category = args.get("root_cause_category")
    if category not in ROOT_CAUSES:
        raise ToolError(f"root_cause_category must be one of {', '.join(ROOT_CAUSES)}")
    cause = _text(args, "root_cause", 500)
    _text(args, "note", 2000, required=False)
    first = "Take ownership of and propose" if f.status == "open" else "Propose"
    return (f"{first} finding {_label(f)} for approval. Root cause: {category.replace('_', ' ')} — "
            f"“{cause.rstrip('.')}”.")


def _exec_propose(session, ctx, p):
    fid = uuid.UUID(p["finding_id"])
    if workflow.lock_finding(session, ctx, fid).status == "open":
        workflow.assign(session, ctx, fid, ctx.user_id)  # same path as Take ownership on the screen
    workflow.transition(session, ctx, fid, "propose", note=p.get("note"),
                        root_cause_category=p["root_cause_category"], root_cause=p["root_cause"])
    return "Proposed for approval."


def _decision(action: str, verb: str, reason_required: bool):
    def prep(session, ctx, args):
        f = _finding(session, ctx, args)
        _can(ctx, f, action)
        note = _text(args, "note", 2000, required=reason_required)
        extra = " This confirms the leakage and prepares a correction." if action == "approve" else ""
        return f"{verb} finding {_label(f)}." + (f" Note: “{note.rstrip('.')}”." if note else "") + extra

    def execute(session, ctx, p):
        f = workflow.transition(session, ctx, uuid.UUID(p["finding_id"]), action, note=p.get("note"))
        return f"Done: the finding is now {f.status}."

    return prep, execute


def _prep_run(session, ctx, args):
    return "Run all checks now on the latest data."


def _exec_run(session, ctx, p):
    engine.request_run(session, ctx.org_id, trigger="manual", requested_by=ctx.user_id)
    return "Check run queued. Results appear in Findings in a few seconds."


def _term(session, ctx, args) -> CommercialTerm:
    try:
        t = get_scoped(session, CommercialTerm, _uuid(args, "term_id"), ctx)
    except HTTPException:
        raise ToolError("No such term in your organization") from None
    if t.status != "proposed":
        raise ToolError(f"This term is already {t.status}")
    return t


def _term_label(t: CommercialTerm) -> str:
    return f"{t.term_type} {t.item_code or '(no item)'} {t.value} {t.currency or ''} from {t.effective_from}".strip()


def _prep_confirm_term(session, ctx, args):
    t = _term(session, ctx, args)
    item = _text(args, "item_code", 80, required=False)
    if not (item or t.item_code) and t.term_type in ("rate", "escalation"):
        raise ToolError("This term needs an item_code before it can be confirmed")
    return (f"Confirm contract term {_term_label(t)}" + (f" for item {item}" if item else "") +
            ". Confirmed terms are used by the next check run.")


def _exec_confirm_term(session, ctx, p):
    edits = {"item_code": p["item_code"]} if p.get("item_code") else {}
    extraction.confirm(session, ctx, uuid.UUID(p["term_id"]), edits, p.get("note"))
    return "Term confirmed."


def _prep_reject_term(session, ctx, args):
    t = _term(session, ctx, args)
    reason = _text(args, "reason", 2000)
    return f"Reject proposed contract term {_term_label(t)}. Reason: “{reason.rstrip('.')}”."


def _exec_reject_term(session, ctx, p):
    extraction.reject(session, ctx, uuid.UUID(p["term_id"]), p["reason"])
    return "Term rejected."


_approve = _decision("approve", "Approve", False)
_reject = _decision("reject", "Reject (not leakage)", True)
_send_back = _decision("send_back", "Send back to the analyst", True)
_write_off = _decision("write_off", "Write off (close without recovery)", True)

NOTE = {"note": {"type": "string", "description": "Short note or reason"}}

TOOLS: tuple[Tool, ...] = (
    Tool("list_findings", "List findings (potential revenue leakage), highest priority first. Filter by status, "
         "check type, customer or minimum value.", (Cap.VIEW_FINDINGS,),
         {"statuses": {"type": "array", "items": {"type": "string", "enum": STATUSES}},
          "check_type": {"type": "string", "enum": CHECK_TYPES},
          "customer_id": {"type": "string"}, "min_value": {"type": "string"},
          "unassigned": {"type": "boolean"}, "limit": {"type": "integer", "minimum": 1, "maximum": 50}},
         read=_list_findings),
    Tool("get_finding", "Full detail of one finding: reason, evidence (agreed/delivered/billed), calculation, "
         "timeline, root cause, correction and the actions available to the user.", (Cap.VIEW_FINDINGS,),
         FINDING_ID, ("finding_id",), read=_get_finding),
    Tool("list_team_and_customers", "The user's own id, people who can own findings, and customers with findings.",
         (Cap.VIEW_FINDINGS,), read=_team),
    Tool("get_outcomes", "Overview figures per currency (cash recovered, potential, confirmed, corrected billing, "
         "closed, prevented recurrence), status counts, monthly trend and top root causes.", (Cap.VIEW_REPORTS,),
         read=_outcomes),
    Tool("get_pricing_opportunities", "Contract prices below the target margin, from cost data. Never leakage.",
         (Cap.VIEW_REPORTS,), read=_pricing),
    Tool("list_corrections", "Recovery tracker: each prepared correction with billed, payments and cash recovered.",
         (Cap.VIEW_RECOVERY,), read=_corrections),
    Tool("list_agreements", "Agreements with customer, versions and terms.", (Cap.VIEW_AGREEMENTS,),
         read=_agreements),
    Tool("list_contract_terms", "Contract terms by status (default proposed: read from documents, awaiting review), "
         "with the passage each came from.", (Cap.VIEW_AGREEMENTS,),
         {"status": {"type": "string", "enum": ["proposed", "confirmed", "rejected"]}}, read=_terms),
    Tool("list_check_runs", "The latest check runs and their results.", (Cap.RUN_CHECKS, Cap.VIEW_FINDINGS),
         read=_runs),
    # Write tools: each only prepares an action for the user to confirm.
    Tool("assign_finding", "Prepare assigning a finding to an owner (use your_user_id to take ownership).",
         (Cap.COMMENT_ASSIGN,), {**FINDING_ID, "owner_id": {"type": ["string", "null"]}}, ("finding_id", "owner_id"),
         prepare=_prep_assign, execute=_exec_assign),
    Tool("comment_on_finding", "Prepare adding a comment to a finding.", (Cap.COMMENT_ASSIGN,),
         {**FINDING_ID, "text": {"type": "string"}}, ("finding_id", "text"),
         prepare=_prep_comment, execute=_exec_comment),
    Tool("propose_finding", "Prepare proposing a finding for approval with a root cause (takes ownership first if "
         "it is open).", (Cap.PROPOSE_REJECT,),
         {**FINDING_ID, "root_cause_category": {"type": "string", "enum": list(ROOT_CAUSES)},
          "root_cause": {"type": "string", "description": "What happened, one or two sentences"}, **NOTE},
         ("finding_id", "root_cause_category", "root_cause"), prepare=_prep_propose, execute=_exec_propose),
    Tool("reject_finding", "Prepare rejecting a finding as not leakage, with a reason.", (Cap.PROPOSE_REJECT,),
         {**FINDING_ID, **NOTE}, ("finding_id", "note"), prepare=_reject[0], execute=_reject[1]),
    Tool("approve_finding", "Prepare approving a proposed finding, which prepares a correction.", (Cap.APPROVE,),
         {**FINDING_ID, **NOTE}, ("finding_id",), prepare=_approve[0], execute=_approve[1]),
    Tool("send_back_finding", "Prepare sending a proposed finding back to the analyst, with a reason.",
         (Cap.APPROVE,), {**FINDING_ID, **NOTE}, ("finding_id", "note"),
         prepare=_send_back[0], execute=_send_back[1]),
    Tool("write_off_finding", "Prepare closing an approved or billed finding without recovery, with a reason.",
         (Cap.APPROVE,), {**FINDING_ID, **NOTE}, ("finding_id", "note"),
         prepare=_write_off[0], execute=_write_off[1]),
    Tool("run_checks", "Prepare running all checks now.", (Cap.RUN_CHECKS,), prepare=_prep_run, execute=_exec_run),
    Tool("confirm_contract_term", "Prepare confirming a proposed contract term (optionally setting its item code).",
         (Cap.MANAGE_CONTRACTS,),
         {"term_id": {"type": "string"}, "item_code": {"type": "string"}, **NOTE}, ("term_id",),
         prepare=_prep_confirm_term, execute=_exec_confirm_term),
    Tool("reject_contract_term", "Prepare rejecting a proposed contract term, with a reason.",
         (Cap.MANAGE_CONTRACTS,), {"term_id": {"type": "string"}, "reason": {"type": "string"}},
         ("term_id", "reason"), prepare=_prep_reject_term, execute=_exec_reject_term),
)
BY_NAME = {t.name: t for t in TOOLS}


def tools_for(role: str) -> list[Tool]:
    return [t for t in TOOLS if t.allowed(role)]
