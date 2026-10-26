"""BE-012: versioned per-org rule configurations; business-type differences are data (FR-15)."""

from tests.factories import add_user, signup


def _rules(client, actor):
    res = client.get("/api/rules", headers=actor.headers)
    assert res.status_code == 200, res.text
    return {r["check_type"]: r for r in res.json()}


def test_version_one_reflects_business_type(client):
    services = client.post("/api/auth/signup", json={
        "organization_name": "Consultancy", "business_type": "professional_services", "name": "A",
        "email": "a1@example.com", "password": "correct-horse-battery"}).json()
    distributor = client.post("/api/auth/signup", json={
        "organization_name": "Distributor", "business_type": "distribution", "name": "B",
        "email": "b1@example.com", "password": "correct-horse-battery"}).json()
    h = lambda t: {"Authorization": f"Bearer {t['access_token']}"}  # noqa: E731
    s_rules = {r["check_type"]: r for r in client.get("/api/rules", headers=h(services)).json()}
    d_rules = {r["check_type"]: r for r in client.get("/api/rules", headers=h(distributor)).json()}
    assert len(s_rules) == 5
    assert s_rules["delivered_not_billed"]["active_version"]["params"]["grace_days"] == 10
    assert d_rules["delivered_not_billed"]["active_version"]["params"]["grace_days"] == 3
    assert s_rules["incorrect_rate"]["active_version"]["params"] == {"unit_price_tolerance": "0.01", "min_value": "0.01"}


def test_change_creates_new_version_and_keeps_history(client):
    admin = signup(client)
    _rules(client, admin)
    res = client.put("/api/rules/delivered_not_billed", headers=admin.headers,
                     json={"params": {"grace_days": 30, "min_value": "5"}})
    assert res.status_code == 200
    rule = res.json()
    assert rule["active_version"]["version_no"] == 2
    assert rule["active_version"]["params"] == {"grace_days": 30, "min_value": "5"}
    assert [v["version_no"] for v in rule["history"]] == [2, 1]
    # Identical params are a no-op.
    again = client.put("/api/rules/delivered_not_billed", headers=admin.headers,
                       json={"params": {"grace_days": 30, "min_value": "5.00"}}).json()
    assert again["active_version"]["version_no"] == 2
    actions = [e["action"] for e in client.get("/api/audit", headers=admin.headers).json()]
    assert actions.count("rule.version_created") == 6


def test_invalid_params_are_rejected(client):
    admin = signup(client)
    for bad in ({"grace_days": -1}, {"grace_days": "soon"}, {"unknown": 1}):
        assert client.put("/api/rules/delivered_not_billed", headers=admin.headers,
                          json={"params": bad}).status_code == 422
    assert client.put("/api/rules/not_a_check", headers=admin.headers, json={"params": {}}).status_code == 422


def test_roles_and_isolation(client):
    admin = signup(client)
    analyst = add_user(client, admin, "analyst")
    assert len(_rules(client, analyst)) == 5
    assert client.put("/api/rules/incorrect_rate", headers=analyst.headers, json={"params": {}}).status_code == 403
    executive = add_user(client, admin, "executive")
    assert client.get("/api/rules", headers=executive.headers).status_code == 403
    client.put("/api/rules/incorrect_rate", headers=admin.headers, json={"params": {"unit_price_tolerance": "1"}})
    other = signup(client)
    assert _rules(client, other)["incorrect_rate"]["active_version"]["version_no"] == 1
