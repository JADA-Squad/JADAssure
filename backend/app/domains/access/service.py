"""Organizations, users and authentication (BE-002)."""

import re
import uuid

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.security import DUMMY_HASH, create_access_token, hash_password, verify_password
from app.core.tenancy import TenantContext, get_scoped, scoped
from app.domains.access.models import Organization, User
from app.domains.access.permissions import ROLE_CAPS
from app.domains.access.schemas import MeOut, OrgOut, SignupIn, TokenOut, UserCreateIn, UserOut, UserUpdateIn
from app.domains.audit import service as audit


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _short_code(session: Session, name: str) -> str:
    base = (re.sub(r"[^A-Z0-9]", "", name.upper()) or "ORG")[:8]
    code, n = base, 1
    while session.scalar(select(func.count()).select_from(Organization).where(Organization.short_code == code)):
        n += 1
        code = f"{base[:8 - len(str(n))]}{n}"
    return code


def _email_taken(session: Session, email: str) -> bool:
    return bool(session.scalar(select(func.count()).select_from(User).where(User.email == email)))


def me(session: Session, user: User) -> MeOut:
    org = session.get(Organization, user.org_id)
    return MeOut(
        user=UserOut.model_validate(user),
        organization=OrgOut.model_validate(org),
        capabilities=sorted(ROLE_CAPS[user.role]),
    )


def _token_for(session: Session, user: User) -> TokenOut:
    token, expires = create_access_token(user.id, user.org_id)
    return TokenOut(access_token=token, expires_at=expires, me=me(session, user))


def create_organization(
    session: Session, *, name: str, business_type: str, is_demo: bool = False, settings: dict | None = None
) -> Organization:
    org = Organization(
        name=name, short_code=_short_code(session, name), business_type=business_type, is_demo=is_demo,
        settings=settings or {},
    )
    session.add(org)
    session.flush()
    return org


def add_user(
    session: Session, *, org_id: uuid.UUID, email: str, name: str, role: str, password: str, actor_id: uuid.UUID | None
) -> User:
    email = _normalize_email(email)
    if _email_taken(session, email):
        raise HTTPException(status.HTTP_409_CONFLICT, "A user with this email already exists")
    user = User(org_id=org_id, email=email, name=name, role=role, password_hash=hash_password(password))
    session.add(user)
    session.flush()
    audit.record(
        session, org_id=org_id, actor_id=actor_id or user.id, action="user.created", entity="user",
        entity_id=user.id, payload={"role": role},
    )
    return user


def signup(session: Session, data: SignupIn) -> TokenOut:
    """FR-01: a new organization together with its first administrator."""
    if _email_taken(session, _normalize_email(data.email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "A user with this email already exists")
    org = create_organization(session, name=data.organization_name, business_type=data.business_type)
    audit.record(
        session, org_id=org.id, actor_id=None, action="organization.created", entity="organization",
        entity_id=org.id, payload={"business_type": org.business_type},
    )
    user = add_user(
        session, org_id=org.id, email=data.email, name=data.name, role="admin", password=data.password, actor_id=None
    )
    session.commit()
    return _token_for(session, user)


def login(session: Session, email: str, password: str) -> TokenOut:
    user = session.scalar(select(User).where(User.email == _normalize_email(email)))
    # Always run one bcrypt check so timing doesn't reveal whether the email exists.
    valid = verify_password(password, user.password_hash if user else DUMMY_HASH)
    if user is None or not valid or not user.active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
    return _token_for(session, user)


def list_users(session: Session, ctx: TenantContext) -> list[User]:
    return list(session.scalars(scoped(User, ctx).order_by(User.created_at)))


def create_user(session: Session, ctx: TenantContext, data: UserCreateIn) -> User:
    user = add_user(
        session, org_id=ctx.org_id, email=data.email, name=data.name, role=data.role, password=data.password,
        actor_id=ctx.user_id,
    )
    session.commit()
    return user


def update_user(session: Session, ctx: TenantContext, user_id: uuid.UUID, data: UserUpdateIn) -> User:
    """FR-02: re-role or deactivate. Admins can't lock themselves out."""
    user = get_scoped(session, User, user_id, ctx)
    changes = data.model_dump(exclude_unset=True, exclude_none=True)
    if user.id == ctx.user_id and (changes.get("active") is False or changes.get("role", "admin") != "admin"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You cannot deactivate or demote your own account")
    for field, value in changes.items():
        setattr(user, field, value)
    if changes:
        audit.record(
            session, org_id=ctx.org_id, actor_id=ctx.user_id, action="user.updated", entity="user",
            entity_id=user.id, payload={k: v for k, v in changes.items() if k in ("role", "active")},
        )
    session.commit()
    return user
