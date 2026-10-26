"""BE-003: permission matrix and tenant scoping on every endpoint (FR-03, GR-06)."""

import re

import pytest
from fastapi.routing import APIRoute

from app.core.tenancy import current_context
from app.domains.access.permissions import ROLE_CAPS, Cap
from app.main import app
from tests.factories import add_user, signup

# design §3.7, restated independently so a silent change to ROLE_CAPS fails this test.
EXPECTED = {
    Cap.MANAGE_USERS_SETTINGS: {"admin"},
    Cap.MANAGE_DATA: {"admin"},
    Cap.MANAGE_CONTRACTS: {"admin", "commercial"},
    Cap.VIEW_AGREEMENTS: {"admin", "analyst", "approver", "commercial"},
    Cap.EDIT_RULES: {"admin"},
    Cap.RUN_CHECKS: {"admin", "analyst"},
    Cap.VIEW_FINDINGS: {"analyst", "approver", "commercial"},
    Cap.COMMENT_ASSIGN: {"analyst", "approver", "commercial"},
    Cap.PROPOSE_REJECT: {"analyst", "commercial"},
    Cap.APPROVE: {"approver"},
    Cap.VIEW_RECOVERY: {"analyst", "approver", "executive"},
    Cap.EXPORT_CORRECTIONS: {"analyst", "approver"},
    Cap.VIEW_REPORTS: {"admin", "analyst", "approver", "commercial", "executive"},
    Cap.VIEW_AUDIT: {"admin", "approver"},
}

PUBLIC_ROUTES = {"/api/health", "/api/auth/signup", "/api/auth/login", "/api/auth/demo-accounts"}


def test_matrix_matches_design():
    actual = {cap: {role for role, caps in ROLE_CAPS.items() if cap in caps} for cap in Cap}
    assert actual == EXPECTED


def test_admin_holds_no_finding_decision_capabilities():
    assert not ROLE_CAPS["admin"] & {Cap.VIEW_FINDINGS, Cap.PROPOSE_REJECT, Cap.APPROVE}


def _dependency_calls(dependant):
    for dep in dependant.dependencies:
        yield dep.call
        yield from _dependency_calls(dep)


def _api_routes():
    return [r for r in app.routes if isinstance(r, APIRoute) and r.path.startswith("/api")]


@pytest.mark.parametrize("route", _api_routes(), ids=lambda r: f"{sorted(r.methods)[0]} {r.path}")
def test_every_non_public_route_requires_authentication(route):
    if route.path in PUBLIC_ROUTES:
        return
    assert current_context in set(_dependency_calls(route.dependant)), f"{route.path} is not authenticated"


@pytest.mark.parametrize("route", _api_routes(), ids=lambda r: f"{sorted(r.methods)[0]} {r.path}")
def test_unauthenticated_requests_are_rejected(client, route):
    if route.path in PUBLIC_ROUTES:
        return
    path = re.sub(r"\{[^}]+\}", "00000000-0000-0000-0000-000000000000", route.path)
    method = sorted(route.methods)[0]
    assert client.request(method, path).status_code == 401


def test_role_without_capability_gets_403(client):
    admin = signup(client)
    for role in ("analyst", "approver", "commercial", "executive"):
        actor = add_user(client, admin, role)
        assert client.get("/api/users", headers=actor.headers).status_code == 403, role
    executive = add_user(client, admin, "executive")
    assert client.get("/api/audit", headers=executive.headers).status_code == 403


def test_cross_org_user_update_is_not_found(client):
    a = signup(client)
    victim = add_user(client, a, "analyst")
    b = signup(client)
    res = client.patch(f"/api/users/{victim.user_id}", headers=b.headers, json={"active": False})
    assert res.status_code == 404
    assert client.get("/api/auth/me", headers=victim.headers).status_code == 200


def test_cross_org_audit_is_invisible(client):
    a = signup(client)
    add_user(client, a, "analyst")
    b = signup(client)
    a_events = client.get("/api/audit", headers=a.headers).json()
    b_events = client.get("/api/audit", headers=b.headers).json()
    assert len(a_events) == 3 and len(b_events) == 2
    assert {e["entity_id"] for e in a_events}.isdisjoint({e["entity_id"] for e in b_events})
    assert client.get("/api/audit/verify", headers=b.headers).json()["events"] == 2
