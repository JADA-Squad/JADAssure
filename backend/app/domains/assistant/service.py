"""Conversations, transcript and confirming prepared actions (BE-034, decision 0009)."""

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.tenancy import TenantContext, scoped
from app.domains.assistant.agent import NOTE_PREFIX
from app.domains.assistant.models import AssistantAction, AssistantConversation
from app.domains.assistant.tools import BY_NAME, ToolError
from app.domains.audit import service as audit

MAX_MESSAGES = 60
TOOL_LABELS = {
    "list_findings": "Looked up findings", "get_finding": "Opened a finding",
    "list_team_and_customers": "Looked up people and customers", "get_outcomes": "Read the overview figures",
    "get_pricing_opportunities": "Read pricing opportunities", "list_corrections": "Read the recovery tracker",
    "list_agreements": "Looked up agreements", "list_contract_terms": "Looked up contract terms",
    "list_check_runs": "Looked up check runs",
}


def conversation(session: Session, ctx: TenantContext, conversation_id: uuid.UUID) -> AssistantConversation:
    """Only the user's own conversation; anything else is 404 (D-5)."""
    conv = session.scalar(scoped(AssistantConversation, ctx).where(AssistantConversation.id == conversation_id,
                                                                   AssistantConversation.user_id == ctx.user_id))
    if conv is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    return conv


def create(session: Session, ctx: TenantContext) -> AssistantConversation:
    conv = AssistantConversation(org_id=ctx.org_id, user_id=ctx.user_id, title="", messages=[], pending_notes=[])
    session.add(conv)
    session.flush()
    return conv


def check_room(conv: AssistantConversation) -> None:
    if len(conv.messages or []) >= MAX_MESSAGES:
        raise HTTPException(status.HTTP_409_CONFLICT, "This conversation is full. Start a new one.")


def action_out(a: AssistantAction) -> dict[str, Any]:
    return {"id": a.id, "tool": a.tool, "summary": a.summary, "status": a.status, "result": a.result,
            "created_at": a.created_at, "decided_at": a.decided_at}


def transcript(session: Session, conv: AssistantConversation) -> list[dict[str, Any]]:
    """What the user sees: their messages, the assistant's text, lookups, and action cards."""
    actions = {a.tool_use_id: a for a in session.scalars(
        select(AssistantAction).where(AssistantAction.conversation_id == conv.id))}
    items: list[dict[str, Any]] = []
    for m in conv.messages or []:
        blocks = m["content"] if isinstance(m["content"], list) else [{"type": "text", "text": m["content"]}]
        for b in blocks:
            kind = b.get("type")
            if m["role"] == "user":
                if kind == "text" and not b["text"].startswith(NOTE_PREFIX):
                    items.append({"kind": "user", "text": b["text"]})
            elif kind == "text" and b.get("text", "").strip():
                items.append({"kind": "assistant", "text": b["text"]})
            elif kind == "tool_use":
                if b["id"] in actions:
                    items.append({"kind": "action", "action": action_out(actions[b["id"]])})
                else:
                    items.append({"kind": "lookup", "text": TOOL_LABELS.get(b["name"], b["name"])})
    return items


def _own_action(session: Session, ctx: TenantContext, action_id: uuid.UUID) -> AssistantAction:
    a = session.scalar(scoped(AssistantAction, ctx).where(AssistantAction.id == action_id,
                                                          AssistantAction.user_id == ctx.user_id)
                       .with_for_update())
    if a is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    if a.status != "proposed":
        raise HTTPException(status.HTTP_409_CONFLICT, f"This action is already {a.status}")
    return a


def _decide(session: Session, ctx: TenantContext, a: AssistantAction, new_status: str, result: str) -> None:
    a.status, a.result, a.decided_at = new_status, result, datetime.now(UTC)
    conv = session.get(AssistantConversation, a.conversation_id)
    if conv is not None:
        conv.pending_notes = [*(conv.pending_notes or []), f"Action {a.id} ({a.tool}) was {new_status}: {result}"]
    audit.record(session, org_id=ctx.org_id, actor_id=ctx.user_id, action=f"assistant.action_{new_status}",
                 entity="assistant_action", entity_id=a.id, payload={"tool": a.tool})


def confirm(session: Session, ctx: TenantContext, action_id: uuid.UUID) -> AssistantAction:
    """The user's click (GR-17): re-check role and state now, then run the existing workflow code."""
    a = _own_action(session, ctx, action_id)
    tool = BY_NAME.get(a.tool)
    try:
        if tool is None or tool.execute is None or not tool.allowed(ctx.role):
            raise ToolError("Your role no longer permits this action")
        with session.begin_nested():
            tool.prepare(session, ctx, a.params)  # type: ignore[misc]  # same checks as when it was prepared
            result = tool.execute(session, ctx, a.params)
    except (ToolError, HTTPException) as exc:
        message = exc.detail if isinstance(exc, HTTPException) else str(exc)
        _decide(session, ctx, a, "failed", str(message))
        return a
    _decide(session, ctx, a, "confirmed", result)
    return a


def cancel(session: Session, ctx: TenantContext, action_id: uuid.UUID) -> AssistantAction:
    a = _own_action(session, ctx, action_id)
    _decide(session, ctx, a, "cancelled", "Cancelled by the user; nothing was changed.")
    return a
