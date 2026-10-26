import uuid
from typing import Any

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, IdMixin, TimestampMixin
from app.core.db_mixins import one_of

ROLES = ("admin", "analyst", "approver", "commercial", "executive")
BUSINESS_TYPES = ("professional_services", "subscription_software", "distribution", "other")


class Organization(IdMixin, TimestampMixin, Base):
    __tablename__ = "organization"
    __table_args__ = (one_of("business_type", BUSINESS_TYPES),)

    name: Mapped[str] = mapped_column(String(200))
    short_code: Mapped[str] = mapped_column(String(12), unique=True)
    business_type: Mapped[str] = mapped_column(String(40), default="other")
    # refresh interval, retention days, ai_provider, materiality (BE-032)
    settings: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)


class User(IdMixin, TimestampMixin, Base):
    __tablename__ = "app_user"
    __table_args__ = (one_of("role", ROLES),)

    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organization.id", ondelete="CASCADE"), index=True
    )
    email: Mapped[str] = mapped_column(String(320), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    password_hash: Mapped[str] = mapped_column(String(100))
    role: Mapped[str] = mapped_column(String(20))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
