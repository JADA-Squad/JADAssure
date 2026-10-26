"""Helpers that create orgs and users through the public API, as a real client would."""

import itertools
from dataclasses import dataclass

from fastapi.testclient import TestClient

PASSWORD = "correct-horse-battery"
_seq = itertools.count(1)


@dataclass
class Actor:
    token: str
    user_id: str
    org_id: str
    role: str
    email: str

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}


def signup(client: TestClient, org_name: str | None = None) -> Actor:
    n = next(_seq)
    email = f"admin{n}@example.com"
    res = client.post(
        "/api/auth/signup",
        json={"organization_name": org_name or f"Org {n}", "name": f"Admin {n}", "email": email, "password": PASSWORD},
    )
    assert res.status_code == 201, res.text
    body = res.json()
    return Actor(body["access_token"], body["me"]["user"]["id"], body["me"]["organization"]["id"], "admin", email)


def add_user(client: TestClient, admin: Actor, role: str) -> Actor:
    n = next(_seq)
    email = f"{role}{n}@example.com"
    res = client.post(
        "/api/users", headers=admin.headers, json={"email": email, "name": f"{role} {n}", "role": role, "password": PASSWORD}
    )
    assert res.status_code == 201, res.text
    return login(client, email, role)


def login(client: TestClient, email: str, role: str) -> Actor:
    res = client.post("/api/auth/login", json={"email": email, "password": PASSWORD})
    assert res.status_code == 200, res.text
    body = res.json()
    return Actor(body["access_token"], body["me"]["user"]["id"], body["me"]["organization"]["id"], role, email)
