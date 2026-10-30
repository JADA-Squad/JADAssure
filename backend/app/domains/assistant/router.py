"""Assistant API (BE-034). Any signed-in user; what the assistant can do depends on their role (D-2)."""

import uuid
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.core.tenancy import TenantContext, current_context, scoped
from app.domains.access.models import Organization
from app.domains.ai import registry
from app.domains.ai.provider import ProviderError
from app.domains.assistant import agent, service
from app.domains.assistant.models import AssistantConversation
from app.domains.assistant.tools import tools_for

router = APIRouter(prefix="/api/assistant", tags=["assistant"])


class StatusOut(BaseModel):
    available: bool
    reason: str | None
    provider: str | None  # e.g. "OpenAI": which external model answers, shown in the panel
    can_change: list[str]
    can_look_up: list[str]


class ConversationSummary(BaseModel):
    id: uuid.UUID
    title: str
    updated_at: datetime


class ActionOut(BaseModel):
    id: uuid.UUID
    tool: str
    summary: str
    status: Literal["proposed", "confirmed", "cancelled", "failed"]
    result: str | None
    created_at: datetime
    decided_at: datetime | None


class ConversationOut(BaseModel):
    id: uuid.UUID
    title: str
    items: list[dict[str, Any]]
    notice: str | None = None


class MessageIn(BaseModel):
    text: str = Field(min_length=1, max_length=4000)


def _view(session: Session, conv: AssistantConversation, notice: str | None = None) -> ConversationOut:
    return ConversationOut(id=conv.id, title=conv.title, items=service.transcript(session, conv), notice=notice)


@router.get("/status", response_model=StatusOut)
def assistant_status(ctx: TenantContext = Depends(current_context), session: Session = Depends(get_session)):
    org = session.get(Organization, ctx.org_id)
    ok, reason = agent.available(org)
    choice = (org.settings if org else {}).get("ai_provider", "stub")
    tools = tools_for(ctx.role)
    return StatusOut(available=ok, reason=reason, provider=registry.EXTERNAL.get(choice, (None,))[0],
                     can_change=[t.name for t in tools if t.writes],
                     can_look_up=[t.name for t in tools if not t.writes])


@router.get("/conversations", response_model=list[ConversationSummary])
def list_conversations(ctx: TenantContext = Depends(current_context), session: Session = Depends(get_session)):
    return list(session.scalars(scoped(AssistantConversation, ctx)
                                .where(AssistantConversation.user_id == ctx.user_id)
                                .order_by(AssistantConversation.updated_at.desc()).limit(20)))


@router.post("/conversations", response_model=ConversationOut, status_code=status.HTTP_201_CREATED)
def new_conversation(ctx: TenantContext = Depends(current_context), session: Session = Depends(get_session)):
    conv = service.create(session, ctx)
    session.commit()
    return _view(session, conv)


@router.get("/conversations/{conversation_id}", response_model=ConversationOut)
def get_conversation(conversation_id: uuid.UUID, ctx: TenantContext = Depends(current_context),
                     session: Session = Depends(get_session)):
    return _view(session, service.conversation(session, ctx, conversation_id))


@router.post("/conversations/{conversation_id}/messages", response_model=ConversationOut)
def send_message(conversation_id: uuid.UUID, data: MessageIn, ctx: TenantContext = Depends(current_context),
                 session: Session = Depends(get_session)):
    """FR-43: one turn of the agent. Reads run now; changes come back as action cards to confirm."""
    conv = service.conversation(session, ctx, conversation_id)
    ok, reason = agent.available(session.get(Organization, ctx.org_id))
    if not ok:
        raise HTTPException(status.HTTP_409_CONFLICT, reason)
    service.check_room(conv)
    try:
        stats = agent.run_turn(session, ctx, conv, data.text.strip())
    except ProviderError as exc:
        session.rollback()
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from None
    session.commit()
    return _view(session, conv, stats["notice"])


@router.post("/actions/{action_id}/confirm", response_model=ActionOut)
def confirm_action(action_id: uuid.UUID, ctx: TenantContext = Depends(current_context),
                   session: Session = Depends(get_session)):
    """GR-17: the user's own click runs the prepared change, re-checked against their role and the record now."""
    a = service.confirm(session, ctx, action_id)
    session.commit()
    return service.action_out(a)


@router.post("/actions/{action_id}/cancel", response_model=ActionOut)
def cancel_action(action_id: uuid.UUID, ctx: TenantContext = Depends(current_context),
                  session: Session = Depends(get_session)):
    a = service.cancel(session, ctx, action_id)
    session.commit()
    return service.action_out(a)
