import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_session
from app.core.tenancy import TenantContext, current_context
from app.domains.access import service
from app.domains.access import settings as org_settings
from app.domains.access.models import Organization, User
from app.domains.access.permissions import Cap, require
from app.domains.access.schemas import LoginIn, MeOut, SignupIn, TokenOut, UserCreateIn, UserOut, UserUpdateIn

auth_router = APIRouter(prefix="/api/auth", tags=["auth"])
users_router = APIRouter(prefix="/api/users", tags=["users"])


@auth_router.post("/signup", response_model=TokenOut, status_code=status.HTTP_201_CREATED)
def signup(data: SignupIn, session: Session = Depends(get_session)):
    if not get_settings().allow_signup:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Signup is disabled")
    return service.signup(session, data)


@auth_router.post("/login", response_model=TokenOut)
def login(data: LoginIn, session: Session = Depends(get_session)):
    return service.login(session, data.email, data.password)


class DemoAccountOut(BaseModel):
    organization: str
    name: str
    email: str
    role: str
    password: str


@auth_router.get("/demo-accounts", response_model=list[DemoAccountOut])
def demo_accounts(session: Session = Depends(get_session)):
    """Seeded DEMO logins for local demos (DATA-001). Empty unless SHOW_DEMO_ACCOUNTS=true; demo orgs only."""
    if not get_settings().show_demo_accounts:
        return []
    from app.seed_demo import DEMO_PASSWORD

    rows = session.execute(
        select(Organization.name, User.name, User.email, User.role)
        .join(User, User.org_id == Organization.id)
        .where(Organization.is_demo.is_(True), User.active.is_(True))
        .order_by(Organization.name, User.role)
    ).all()
    return [DemoAccountOut(organization=o, name=n, email=e, role=r, password=DEMO_PASSWORD) for o, n, e, r in rows]


@auth_router.get("/me", response_model=MeOut)
def me(ctx: TenantContext = Depends(current_context), session: Session = Depends(get_session)):
    return service.me(session, session.get(User, ctx.user_id))


@users_router.get("", response_model=list[UserOut])
def list_users(
    ctx: TenantContext = Depends(require(Cap.MANAGE_USERS_SETTINGS)), session: Session = Depends(get_session)
):
    return service.list_users(session, ctx)


@users_router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(
    data: UserCreateIn,
    ctx: TenantContext = Depends(require(Cap.MANAGE_USERS_SETTINGS)),
    session: Session = Depends(get_session),
):
    return service.create_user(session, ctx, data)


@users_router.patch("/{user_id}", response_model=UserOut)
def update_user(
    user_id: uuid.UUID,
    data: UserUpdateIn,
    ctx: TenantContext = Depends(require(Cap.MANAGE_USERS_SETTINGS)),
    session: Session = Depends(get_session),
):
    return service.update_user(session, ctx, user_id, data)


# ---------------------------------------------------------------- settings (BE-032)

settings_router = APIRouter(prefix="/api/settings", tags=["settings"])


class DeleteDataIn(BaseModel):
    confirm_short_code: str


@settings_router.get("", response_model=org_settings.SettingsOut)
def get_settings_(ctx: TenantContext = Depends(require(Cap.MANAGE_USERS_SETTINGS)),
                  session: Session = Depends(get_session)):
    return org_settings.read(session.get(Organization, ctx.org_id))


@settings_router.put("", response_model=org_settings.SettingsOut)
def update_settings(data: org_settings.SettingsIn, ctx: TenantContext = Depends(require(Cap.MANAGE_USERS_SETTINGS)),
                    session: Session = Depends(get_session)):
    out = org_settings.update(session, ctx, data)
    session.commit()
    return out


@settings_router.post("/delete-organization-data")
def delete_organization_data(data: DeleteDataIn, ctx: TenantContext = Depends(require(Cap.MANAGE_USERS_SETTINGS)),
                             session: Session = Depends(get_session)):
    """FR-41: irreversible. Removes every record and file of the org; all its users are signed out."""
    result = org_settings.delete_organization_data(session, ctx, data.confirm_short_code)
    session.commit()
    return result
