"""Rule configurations, check runs and findings (design §3.2, §2.5)."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import CHAR, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, IdMixin, TimestampMixin
from app.core.db_mixins import OrgScopedMixin, currency_column, one_of
from app.core.money import Money

CHECK_TYPES = ("delivered_not_billed", "incorrect_rate", "expired_discount", "missed_increase", "credit_outside_policy")
FAMILIES = ("unbilled", "price", "credit")
CONFIDENCE = ("high", "medium", "low")
FINDING_STATUSES = ("open", "in_review", "proposed", "approved", "billed", "recovered", "rejected", "closed_no_recovery")
TERMINAL_STATUSES = ("rejected", "recovered", "closed_no_recovery")
RUN_STATUSES = ("queued", "running", "succeeded", "failed")


class Rule(IdMixin, TimestampMixin, OrgScopedMixin, Base):
    __tablename__ = "rule"
    __table_args__ = (UniqueConstraint("org_id", "check_type", name="uq_rule_org_check"), one_of("check_type", CHECK_TYPES))

    check_type: Mapped[str] = mapped_column(String(40))
    active_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("rule_version.id", use_alter=True, ondelete="SET NULL"), nullable=True
    )


class RuleVersion(IdMixin, TimestampMixin, OrgScopedMixin, Base):
    __tablename__ = "rule_version"
    __table_args__ = (UniqueConstraint("rule_id", "version_no", name="uq_rule_version_no"),)

    rule_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("rule.id", ondelete="CASCADE"), index=True)
    version_no: Mapped[int] = mapped_column(Integer)
    params: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)


class CheckRun(IdMixin, TimestampMixin, OrgScopedMixin, Base):
    __tablename__ = "check_run"
    __table_args__ = (one_of("trigger", ("manual", "schedule")), one_of("status", RUN_STATUSES))

    trigger: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20))
    rule_version_ids: Mapped[list[str]] = mapped_column(JSONB, default=list)
    stats: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    error: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    requested_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)


class Finding(IdMixin, TimestampMixin, OrgScopedMixin, Base):
    __tablename__ = "finding"
    __table_args__ = (
        UniqueConstraint("org_id", "fingerprint", name="uq_finding_org_fingerprint"),
        one_of("family", FAMILIES),
        one_of("check_type", CHECK_TYPES),
        one_of("confidence", CONFIDENCE),
        one_of("status", FINDING_STATUSES),
    )

    fingerprint: Mapped[str] = mapped_column(CHAR(64))
    family: Mapped[str] = mapped_column(String(20))
    check_type: Mapped[str] = mapped_column(String(40))
    also_detected_by: Mapped[list[str]] = mapped_column(ARRAY(String(40)), default=list)
    customer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customer.id", ondelete="CASCADE"), nullable=True, index=True
    )
    agreement_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agreement.id", ondelete="SET NULL"), nullable=True
    )
    item_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    period_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    period_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    value: Mapped[Decimal] = mapped_column(Money)
    currency: Mapped[str] = currency_column()
    confidence: Mapped[str] = mapped_column(String(10))
    reason: Mapped[str] = mapped_column(Text)
    calculation: Mapped[dict[str, Any]] = mapped_column(JSONB)
    evidence: Mapped[dict[str, Any]] = mapped_column(JSONB)
    rule_version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("rule_version.id"))
    recommended_action: Mapped[str] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(20), index=True)
    owner_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("app_user.id"), nullable=True)
    proposer_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("app_user.id"), nullable=True)
    root_cause: Mapped[str | None] = mapped_column(String(500), nullable=True)
    recurrence_of_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("finding.id", ondelete="SET NULL"), nullable=True
    )
    first_run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("check_run.id"))
    last_run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("check_run.id"))
    # Labelled AI text (FR-40); never read by any calculation (GR-02).
    ai_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
