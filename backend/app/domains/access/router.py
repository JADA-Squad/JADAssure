import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_session
from app.core.tenancy import TenantContext, current_context
from app.domains.access import service
from app.domains.access.models import User
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
