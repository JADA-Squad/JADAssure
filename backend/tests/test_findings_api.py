"""BE-020: findings queue with filters and priority; detail with evidence, timeline and comments."""

from datetime import date

from sqlalchemy import select, update

from app.domains.access.models import Organization
from app.domains.rules.models import Finding
from app.seed_demo import DEMO_PASSWORD, demo_email, main as seed
from tests.engine_helpers import run
from tests.factories import Actor, add_user, signup


def _demo_actor(client, role: str, slug: str) -> Actor:
    res = client.post("/api/auth/login", json={"email": demo_email(role, slug), "password": DEMO_PASSWORD})
    body = res.json()
    return Actor(body["access_token"], body["me"]["user"]["id"], body["me"]["organization"]["id"], role, "")


def _seeded(client, session):
    seed()
    for org in session.scalars(select(Organization)):
        run(org.id, date(2026, 10, 26))
    return _demo_actor(client, "analyst", "ridgeline")


def test_queue_is_prioritised_and_filterable(client, session):
    analyst = _seeded(client, session)
    page = client.get("/api/findings", headers=analyst.headers).json()
    assert page["total"] == 4 and page["value_by_currency"] == {"USD": "1432.5000"}
    values = [i["value"] for i in page["items"]]
    assert values == ["750.0000", "375.0000", "187.5000", "120.0000"]  # all high confidence → value order
    assert page["items"][0]["customer_name"] == "Corbel Hardware"

    q = lambda **p: client.get("/api/findings", headers=analyst.headers, params=p).json()  # noqa: E731
    assert q(check_type="expired_discount")["total"] == 2
    assert q(min_value="200")["total"] == 2
    assert q(max_value="200")["total"] == 2
    assert q(confidence="medium")["total"] == 0
    assert q(status=["open"])["total"] == 4 and q(status=["rejected"])["total"] == 0
    assert q(unassigned="true")["total"] == 4
    assert q(max_age_days=1)["total"] == 4 and q(min_age_days=1)["total"] == 0
    filters = client.get("/api/findings/filters", headers=analyst.headers).json()
    assert [c["name"] for c in filters["customers"]] == ["Corbel Hardware"]
    assert q(customer_id=filters["customers"][0]["id"])["total"] == 4
    assert {o["name"] for o in filters["owners"]} >= {"Ana Analyst (demo)"}
    assert q(limit=2, offset=2)["items"][0]["value"] == "187.5000"


def test_priority_weights_confidence(client, session):
    analyst = _seeded(client, session)
    org_id = analyst.org_id
    session.execute(update(Finding).where(Finding.org_id == org_id, Finding.value == 750).values(confidence="low"))
    session.commit()
    items = client.get("/api/findings", headers=analyst.headers).json()["items"]
    assert [i["value"] for i in items][:2] == ["375.0000", "750.0000"]  # 750 × 0.4 = 300 < 375
    assert items[1]["priority"] == "300.0000"


def test_detail_has_evidence_calculation_timeline_and_comments(client, session):
    analyst = _seeded(client, session)
    fid = next(i["id"] for i in client.get("/api/findings", headers=analyst.headers).json()["items"]
               if i["value"] == "375.0000")
    d = client.get(f"/api/findings/{fid}", headers=analyst.headers).json()
    assert d["check_type"] == "expired_discount" and d["calculation"]["result"] == "375"
    assert d["evidence"]["billed"][0]["invoice_number"] == "RDG-1010"
    assert d["evidence"]["agreement"]["source_record_id"] == "RS-A1"
    assert d["rule_version"]["version_no"] == 1
    assert [t["kind"] for t in d["timeline"]] == ["detected"]

    res = client.post(f"/api/findings/{fid}/comments", headers=analyst.headers,
                      json={"body": "Checked with sales: promo was not extended."})
    assert res.status_code == 201
    tl = res.json()["timeline"]
    assert [t["kind"] for t in tl] == ["detected", "comment"] and tl[1]["actor_name"] == "Ana Analyst (demo)"
    assert client.post(f"/api/findings/{fid}/comments", headers=analyst.headers, json={"body": ""}).status_code == 422


def test_findings_roles_and_isolation(client, session):
    analyst = _seeded(client, session)
    fid = client.get("/api/findings", headers=analyst.headers).json()["items"][0]["id"]
    cirrus = _demo_actor(client, "approver", "cirrus")
    assert client.get(f"/api/findings/{fid}", headers=cirrus.headers).status_code == 404
    assert client.post(f"/api/findings/{fid}/comments", headers=cirrus.headers, json={"body": "x"}).status_code == 404
    assert {i["customer_name"] for i in client.get("/api/findings", headers=cirrus.headers).json()["items"]} == {
        "Bluefin Logistics"}
    for role in ("admin", "executive"):
        actor = _demo_actor(client, role, "ridgeline")
        assert client.get("/api/findings", headers=actor.headers).status_code == 403
    assert client.get("/api/findings", headers=_demo_actor(client, "commercial", "ridgeline").headers).status_code == 200
    stranger = signup(client)
    assert client.get("/api/findings", headers=add_user(client, stranger, "analyst").headers).json()["total"] == 0
