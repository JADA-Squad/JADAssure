"""Assistant conversations and the actions it prepares (BE-034, decision 0009)."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, IdMixin, TimestampMixin
from app.core.db_mixins import OrgScopedMixin, one_of

ACTION_STATUSES = ("proposed", "confirmed", "cancelled", "failed")


class AssistantConversation(IdMixin, TimestampMixin, OrgScopedMixin, Base):
    """One user's chat. `messages` is the Claude message history, appended to and never edited."""

    __tablename__ = "assistant_conversation"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("app_user.id", ondelete="CASCADE"),
                                               index=True)
    title: Mapped[str] = mapped_column(String(200), default="")
    messages: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    # Outcomes of confirmed/cancelled actions, told to the model with the user's next message.
    pending_notes: Mapped[list[str]] = mapped_column(JSONB, default=list)


class AssistantAction(IdMixin, TimestampMixin, OrgScopedMixin, Base):
    """A change the assistant prepared. It runs only when the same user confirms it (GR-17)."""

    __tablename__ = "assistant_action"
    __table_args__ = (one_of("status", ACTION_STATUSES),)

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assistant_conversation.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("app_user.id", ondelete="CASCADE"))
    tool_use_id: Mapped[str] = mapped_column(String(100))
    tool: Mapped[str] = mapped_column(String(60))
    params: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    summary: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="proposed")
    result: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
