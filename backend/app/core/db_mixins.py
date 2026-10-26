"""Column mixins shared by domain models (design §3.2, decision 0001 D-9)."""

import uuid
from typing import Any

from sqlalchemy import CHAR, CheckConstraint, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, declared_attr, mapped_column


class OrgScopedMixin:
    """Every tenant-owned row carries org_id (GR-06). Rows go when their org's data is deleted (FR-41)."""

    @declared_attr
    def org_id(cls) -> Mapped[uuid.UUID]:
        return mapped_column(
            UUID(as_uuid=True), ForeignKey("organization.id", ondelete="CASCADE"), index=True, nullable=False
        )


class SourceMixin:
    """Pointer back to the original record (GR-16) and the idempotency key for re-imports (GR-11)."""

    @declared_attr
    def data_source_id(cls) -> Mapped[uuid.UUID | None]:
        return mapped_column(UUID(as_uuid=True), ForeignKey("data_source.id", ondelete="CASCADE"), nullable=True)

    @declared_attr
    def import_id(cls) -> Mapped[uuid.UUID | None]:
        return mapped_column(UUID(as_uuid=True), ForeignKey("import_batch.id", ondelete="SET NULL"), nullable=True)

    source_record_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    source_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    source_hash: Mapped[str | None] = mapped_column(CHAR(64), nullable=True)


def source_key(table: str) -> UniqueConstraint:
    return UniqueConstraint("org_id", "data_source_id", "source_record_id", name=f"uq_{table}_source_key")


def one_of(column: str, values: tuple[str, ...], name: str | None = None) -> CheckConstraint:
    quoted = ", ".join(f"'{v}'" for v in values)
    return CheckConstraint(f"{column} IN ({quoted})", name=name or f"{column}_valid")


def currency_column() -> Mapped[str]:
    return mapped_column(CHAR(3), nullable=False)
