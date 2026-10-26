"""Password hashing and access tokens (NFR-12, decision 0001 D-5)."""

import uuid
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt

from app.core.config import get_settings

_ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("ascii")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("ascii"))
    except ValueError:
        return False


# Equalizes login timing when the email is unknown, so responses don't reveal which accounts exist.
DUMMY_HASH = hash_password("timing-equalizer-not-a-real-password")


def create_access_token(user_id: uuid.UUID, org_id: uuid.UUID) -> tuple[str, datetime]:
    settings = get_settings()
    now = datetime.now(UTC)
    expires = now + timedelta(minutes=settings.jwt_expires_minutes)
    claims = {"sub": str(user_id), "org": str(org_id), "iat": now, "exp": expires}
    return jwt.encode(claims, settings.jwt_secret, algorithm=_ALGORITHM), expires


def decode_access_token(token: str) -> dict:
    """Raises jwt.PyJWTError on any invalid, tampered or expired token."""
    return jwt.decode(
        token, get_settings().jwt_secret, algorithms=[_ALGORITHM], options={"require": ["sub", "org", "exp"]}
    )
