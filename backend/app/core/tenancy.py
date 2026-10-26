"""Tenant context and org-scoped data access (GR-06, decision 0001 D-7).

The org id comes only from the authenticated token, checked against the user row. Never accept an
org id from request input. Every read of tenant data goes through `scoped` or `get_scoped`.
"""

import uuid
from dataclasses import dataclass
from typing import Any, TypeVar

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.core.security import decode_access_token

T = TypeVar("T")

_bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class TenantContext:
    user_id: uuid.UUID
    org_id: uuid.UUID
    role: str


def _unauthorized() -> HTTPException:
    return HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated", headers={"WWW-Authenticate": "Bearer"})


def current_context(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    session: Session = Depends(get_session),
) -> TenantContext:
    from app.domains.access.models import User  # local import: core must not depend on domains at import time

    if credentials is None:
        raise _unauthorized()
    try:
        claims = decode_access_token(credentials.credentials)
        user_id = uuid.UUID(claims["sub"])
        org_id = uuid.UUID(claims["org"])
    except (jwt.PyJWTError, ValueError, KeyError):
        raise _unauthorized() from None

    user = session.get(User, user_id)
    if user is None or not user.active or user.org_id != org_id:
        raise _unauthorized()
    # Role is read from the database so a role change takes effect immediately.
    return TenantContext(user_id=user.id, org_id=user.org_id, role=user.role)


def scoped(model: type[T], ctx: TenantContext) -> Select[tuple[T]]:
    """SELECT restricted to the caller's organization."""
    return select(model).where(model.org_id == ctx.org_id)  # type: ignore[attr-defined]


def get_scoped(session: Session, model: type[T], entity_id: Any, ctx: TenantContext) -> T:
    """Fetch one row of the caller's organization, or 404 (never reveal another org's rows exist)."""
    obj = session.scalar(scoped(model, ctx).where(model.id == entity_id))  # type: ignore[attr-defined]
    if obj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    return obj
