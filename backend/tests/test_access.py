"""BE-002: signup, login with expiring JWT, and user management (FR-01, FR-02, NFR-12)."""

import uuid
from datetime import UTC, datetime, timedelta

import jwt
from sqlalchemy import select

from app.core.config import get_settings
from app.domains.access.models import Organization, User
from tests.factories import PASSWORD, add_user, signup


def test_signup_creates_org_and_admin(client, session):
    admin = signup(client, "Acme Holdings")

    org = session.get(Organization, uuid.UUID(admin.org_id))
    user = session.get(User, uuid.UUID(admin.user_id))
    assert org.name == "Acme Holdings" and org.short_code == "ACMEHOLD"
    assert user.role == "admin" and user.org_id == org.id
    assert user.password_hash != PASSWORD and user.password_hash.startswith("$2")


def test_short_codes_stay_unique(client, session):
    signup(client, "Acme Holdings")
    second = signup(client, "Acme Holdings")
    assert session.get(Organization, uuid.UUID(second.org_id)).short_code == "ACMEHOL2"


def test_login_and_me(client):
    admin = signup(client)
    res = client.get("/api/auth/me", headers=admin.headers)
    assert res.status_code == 200
    body = res.json()
    assert body["user"]["email"] == admin.email
    assert "manage_users_settings" in body["capabilities"]


def test_login_rejects_bad_password_and_unknown_email_identically(client):
    admin = signup(client)
    wrong = client.post("/api/auth/login", json={"email": admin.email, "password": "not-the-password"})
    unknown = client.post("/api/auth/login", json={"email": "nobody@example.com", "password": "whatever-123"})
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()


def test_expired_token_is_rejected(client):
    admin = signup(client)
    past = datetime.now(UTC) - timedelta(minutes=1)
    expired = jwt.encode(
        {"sub": admin.user_id, "org": admin.org_id, "iat": past - timedelta(hours=1), "exp": past},
        get_settings().jwt_secret,
        algorithm="HS256",
    )
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {expired}"}).status_code == 401


def test_token_signed_with_other_secret_is_rejected(client):
    admin = signup(client)
    forged = jwt.encode(
        {"sub": admin.user_id, "org": admin.org_id, "exp": datetime.now(UTC) + timedelta(hours=1)},
        "x" * 64,
        algorithm="HS256",
    )
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {forged}"}).status_code == 401


def test_admin_creates_rerole_and_deactivates_user(client, session):
    admin = signup(client)
    analyst = add_user(client, admin, "analyst")

    res = client.patch(f"/api/users/{analyst.user_id}", headers=admin.headers, json={"role": "approver"})
    assert res.status_code == 200 and res.json()["role"] == "approver"
    # Role change applies immediately to the existing token.
    assert client.get("/api/auth/me", headers=analyst.headers).json()["user"]["role"] == "approver"

    res = client.patch(f"/api/users/{analyst.user_id}", headers=admin.headers, json={"active": False})
    assert res.status_code == 200
    assert client.get("/api/auth/me", headers=analyst.headers).status_code == 401
    login = client.post("/api/auth/login", json={"email": analyst.email, "password": PASSWORD})
    assert login.status_code == 401


def test_duplicate_email_rejected(client):
    admin = signup(client)
    res = client.post(
        "/api/users",
        headers=admin.headers,
        json={"email": admin.email.upper(), "name": "Dup", "role": "analyst", "password": PASSWORD},
    )
    assert res.status_code == 409


def test_admin_cannot_lock_themselves_out(client):
    admin = signup(client)
    for change in ({"active": False}, {"role": "analyst"}):
        assert client.patch(f"/api/users/{admin.user_id}", headers=admin.headers, json=change).status_code == 400


def test_admin_corrects_name_and_email(client):
    admin = signup(client)
    analyst = add_user(client, admin, "analyst")
    other = add_user(client, admin, "approver")
    url = f"/api/users/{analyst.user_id}"
    res = client.patch(url, headers=admin.headers, json={"name": "  Ana Fixed ", "email": "Ana.Fixed@Example.com"})
    assert res.status_code == 200, res.text
    assert (res.json()["name"], res.json()["email"]) == ("Ana Fixed", "ana.fixed@example.com")
    # The corrected email signs in; the old one no longer does.
    assert client.post("/api/auth/login", json={"email": "ana.fixed@example.com", "password": PASSWORD}).status_code == 200
    assert client.post("/api/auth/login", json={"email": analyst.email, "password": PASSWORD}).status_code == 401
    # Duplicates, blanks and bad emails are refused; an admin may correct their own name.
    assert client.patch(url, headers=admin.headers, json={"email": other.email}).status_code == 409
    assert client.patch(url, headers=admin.headers, json={"name": "   "}).status_code == 422
    assert client.patch(url, headers=admin.headers, json={"email": "not-an-email"}).status_code == 422
    assert client.patch(f"/api/users/{admin.user_id}", headers=admin.headers, json={"name": "Admin Fixed"}).status_code == 200
    # Audited without the personal values; only admins may edit.
    event = next(e for e in client.get("/api/audit", headers=admin.headers).json()
                 if e["action"] == "user.updated" and e["entity_id"] == analyst.user_id)
    assert event["payload"] == {"changed": ["email", "name"]}
    assert client.patch(url, headers=other.headers, json={"name": "Hacked"}).status_code == 403


def test_weak_password_rejected(client):
    res = client.post(
        "/api/auth/signup",
        json={"organization_name": "Short", "name": "A", "email": "a@example.com", "password": "short"},
    )
    assert res.status_code == 422


def test_users_listing_is_org_scoped(client, session):
    a = signup(client)
    add_user(client, a, "analyst")
    b = signup(client)
    emails = {u["email"] for u in client.get("/api/users", headers=b.headers).json()}
    assert emails == {b.email}
    assert len(session.scalars(select(User)).all()) == 3
