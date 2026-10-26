"""BE-026: pricing opportunities from contracted price vs cost; separate from leakage (FR-33)."""

from datetime import date
from decimal import Decimal

from sqlalchemy import select

from app.domains.access.models import Organization
from app.domains.reporting import pricing
from app.seed_demo import main as seed
from tests.factories import signup
from tests.test_recovery import _demo


def test_beyon_opportunities_from_cost_data(client, session):
    seed([])
    beyon = session.scalar(select(Organization).where(Organization.name == "Beyon"))
    result = pricing.opportunities(session, beyon.id, today=date(2026, 10, 26))
    assert result["has_cost_data"] and result["target_margin_pct"] == "20"
    got = {(o["item_code"], o["currency"]): o for o in result["opportunities"]}
    assert set(got) == {("WIDGET-A", "USD"), ("WIDGET-A", "CAD")}  # WIDGET-B clears 20% in both currencies
    usd = got[("WIDGET-A", "USD")]
    assert (usd["contracted_net_price"], usd["unit_cost"], usd["margin_pct"]) == ("12.500000", "11.800000", "5.6")
    assert usd["suggested_price"] == "14.750000" and usd["billed_quantity_12m"] == "870.000000"
    assert usd["indicative_annual_uplift"] == "1957.5000" and usd["below_cost"] is False
    cad = got[("WIDGET-A", "CAD")]
    assert (cad["margin_pct"], cad["suggested_price"], cad["indicative_annual_uplift"]) == ("15.6", "16.875000", "350.0000")
    assert result["items_without_cost"] == []


def test_opportunities_need_cost_data_and_never_touch_leakage(client, session):
    seed([])
    jm_exec = _demo(client, "executive", "jm.com")
    body = client.get("/api/reports/pricing-opportunities", headers=jm_exec.headers).json()
    assert body["has_cost_data"] is False and body["opportunities"] == []
    assert {i["item_code"] for i in body["items_without_cost"]} >= {"SENIOR-CONSULT", "PLATFORM-SEAT"}

    beyon_exec = _demo(client, "executive", "beyon.com")
    before = client.get("/api/reports/outcomes", headers=beyon_exec.headers).json()
    assert len(client.get("/api/reports/pricing-opportunities", headers=beyon_exec.headers).json()["opportunities"]) == 2
    assert client.get("/api/reports/outcomes", headers=beyon_exec.headers).json() == before


def test_target_margin_is_configurable(client, session):
    seed([])
    admin = _demo(client, "admin", "beyon.com")
    r = client.put("/api/settings", headers=admin.headers, json={"pricing_target_margin_pct": "35"})
    assert r.status_code == 200 and r.json()["pricing_target_margin_pct"] == "35"
    ops = client.get("/api/reports/pricing-opportunities", headers=admin.headers).json()["opportunities"]
    assert {o["item_code"] for o in ops} == {"WIDGET-A", "WIDGET-B"}  # WIDGET-B's ~30% is now below target
    assert client.put("/api/settings", headers=admin.headers, json={"pricing_target_margin_pct": "95"}).status_code == 422
    other = signup(client)
    assert client.get("/api/reports/pricing-opportunities", headers=other.headers).json()["opportunities"] == []
