"""BE-014..BE-019: the five checks, de-duplication, evidence and idempotent re-runs."""

from datetime import date
from decimal import Decimal

from sqlalchemy import update

from app.domains.rules.models import Finding
from tests.engine_helpers import findings, load_world, run
from tests.factories import signup

D = Decimal
RATE_TERMS = (
    "term_id,version_id,item_code,term_type,value,unit,currency,effective_from,effective_to,approval_ref,max_value\n"
    "T1,V1,HOURS,rate,180,hour,USD,2026-01-01,,,\n"
    "T2,V1,SEAT,rate,45,seat,USD,2026-01-01,,,\n"
    "T3,V1,SEAT,escalation,5,pct,,2026-07-01,,RENEW,\n"
    "T4,V2,WIDGET,rate,12.50,unit,USD,2026-01-01,,,\n"
    "T5,V2,WIDGET,discount,10,pct,,2026-01-01,2026-03-31,PROMO,\n"
    "T6,V2,,credit_policy,500,,USD,2026-01-01,,POLICY,2000\n"
)
INVOICES_HEAD = "invoice_id,customer_id,number,invoice_date,currency\n"
LINES_HEAD = ("line_id,invoice_id,agreement_id,item_code,quantity,unit_price,discount_pct,net_amount,tax_amount,"
              "service_period_start,service_period_end\n")
EVENTS_HEAD = "event_id,customer_id,agreement_id,item_code,quantity,unit,service_date,billing_date,currency\n"


def _world(client, events="", invoices="", lines="", credits=""):
    admin = signup(client)
    extra = {"commercial_term": RATE_TERMS}
    if events:
        extra["billable_event"] = EVENTS_HEAD + events
    if invoices:
        extra["invoice"] = INVOICES_HEAD + invoices
    if lines:
        extra["invoice_line"] = LINES_HEAD + lines
    if credits:
        extra["credit"] = "credit_id,customer_id,invoice_id,amount,currency,reason_code,approval_ref,credit_date\n" + credits
    load_world(client, admin, extra)
    return admin


# ---------------------------------------------------------------- BE-014 delivered not billed

UNBILLED = dict(
    events="E1,C1,A1,HOURS,40,hour,2026-04-15,2026-04-30,USD\nE2,C1,A1,HOURS,12,hour,2026-04-28,2026-04-30,USD\n",
    invoices="I1,C1,INV-1,2026-05-03,USD\n",
    lines="L1,I1,A1,HOURS,40,180,,7200,0,2026-04-01,2026-04-30\n",
)


def test_unbilled_respects_grace_then_values_shortfall(client, session):
    admin = _world(client, **UNBILLED)
    run(admin.org_id, date(2026, 5, 10))  # billing due 04-30 + 15 grace days = 05-15
    assert findings(session, admin.org_id) == []

    r = run(admin.org_id, date(2026, 5, 16))
    [f] = findings(session, admin.org_id)
    assert (f.check_type, f.family, f.value, f.currency, f.confidence) == (
        "delivered_not_billed", "unbilled", D("2160.0000"), "USD", "high")
    assert f.calculation["inputs"]["unbilled"] == "12" and f.calculation["result"] == "2160"
    assert [e["source_record_id"] for e in f.evidence["delivered"]] == ["E1", "E2"]
    assert [b["source_record_id"] for b in f.evidence["billed"]] == ["L1"]
    assert f.evidence["terms"][0]["source_record_id"] == "T1"
    assert "12 hour of HOURS delivered in April 2026" in f.reason
    assert f.first_run_id == r.id and f.period_start == date(2026, 4, 1)


def test_unbilled_with_inferred_agreement_is_medium_confidence(client, session):
    admin = _world(client, events="E1,C1,,HOURS,10,hour,2026-04-15,2026-04-30,USD\n")
    run(admin.org_id, date(2026, 6, 1))
    [f] = findings(session, admin.org_id)
    assert f.confidence == "medium" and f.value == D("1800")


# ---------------------------------------------------------------- BE-015 incorrect rate

def test_incorrect_rate_net_of_tax(client, session):
    admin = _world(client, invoices="I1,C1,INV-1,2026-03-01,USD\n",
                   lines="L1,I1,A1,SEAT,120,40,,4800,384,2026-03-01,2026-03-31\n")
    run(admin.org_id, date(2026, 10, 26))
    [f] = findings(session, admin.org_id)
    assert (f.check_type, f.value, f.also_detected_by) == ("incorrect_rate", D("600"), [])
    assert f.calculation["components"] == {"rate": "600", "discount": "0"}


def test_no_rate_finding_for_overbilling_tolerance_or_other_currency(client, session):
    admin = _world(client, invoices="I1,C1,INV-1,2026-03-01,USD\nI2,C1,INV-2,2026-04-01,EUR\nI3,C1,INV-3,2026-05-01,USD\n",
                   lines=("L1,I1,A1,SEAT,10,50,,500,0,2026-03-01,2026-03-31\n"
                          "L2,I2,A1,SEAT,10,30,,300,0,2026-04-01,2026-04-30\n"
                          "L3,I3,A1,SEAT,10,44.995,,449.95,0,2026-05-01,2026-05-31\n"))
    r = run(admin.org_id, date(2026, 10, 26))
    assert findings(session, admin.org_id) == []
    assert r.stats["skipped"] == {"currency_mismatch": 1}


# ---------------------------------------------------------------- BE-016 expired / unauthorized discount

def test_expired_and_excess_discounts(client, session):
    admin = _world(client, invoices="I1,C1,R-1,2026-02-12,USD\nI2,C1,R-2,2026-04-14,USD\nI3,C1,R-3,2026-03-01,USD\n",
                   lines=("L1,I1,A2,WIDGET,200,12.50,10,2250,0,2026-02-12,2026-02-12\n"    # valid promo
                          "L2,I2,A2,WIDGET,300,12.50,10,3375,0,2026-04-14,2026-04-14\n"    # expired
                          "L3,I3,A2,WIDGET,300,12.50,15,3187.50,0,2026-03-01,2026-03-01\n"))  # above approved
    run(admin.org_id, date(2026, 10, 26))
    got = sorted((f.check_type, f.value) for f in findings(session, admin.org_id))
    assert got == [("expired_discount", D("187.5")), ("expired_discount", D("375"))]


# ---------------------------------------------------------------- BE-017 missed increase + dedup (BE-019)

def test_missed_increase_absorbs_incorrect_rate(client, session):
    admin = _world(client, invoices="I1,C1,INV-7,2026-07-01,USD\nI2,C1,INV-6,2026-06-01,USD\n",
                   lines=("L1,I1,A1,SEAT,120,45,,5400,0,2026-07-01,2026-07-31\n"
                          "L2,I2,A1,SEAT,120,45,,5400,0,2026-06-01,2026-06-30\n"))
    run(admin.org_id, date(2026, 10, 26))
    [f] = findings(session, admin.org_id)
    assert (f.check_type, f.also_detected_by, f.value) == ("missed_increase", ["incorrect_rate"], D("270"))
    assert {t["term_type"] for t in f.evidence["terms"]} == {"rate", "escalation"}


def test_two_causes_on_one_line_count_once(client, session):
    # Wrong unit price (12.00 vs 12.50) AND an expired 10% discount on the same line.
    admin = _world(client, invoices="I1,C1,R-9,2026-05-01,USD\n",
                   lines="L1,I1,A2,WIDGET,100,12.00,10,1080,0,2026-05-01,2026-05-01\n")
    run(admin.org_id, date(2026, 10, 26))
    [f] = findings(session, admin.org_id)
    assert f.check_type == "expired_discount" and f.also_detected_by == ["incorrect_rate"]
    assert f.value == D("170")  # expected 1250 − billed 1080, not 50 + 120 counted separately
    assert f.calculation["components"] == {"rate": "50", "discount": "120"}


# ---------------------------------------------------------------- BE-018 credit outside policy

def test_credit_policy(client, session):
    admin = _world(client, invoices="I1,C1,R-1,2026-03-09,USD\n",
                   lines="L1,I1,A2,WIDGET,80,12.50,,1000,0,2026-03-09,2026-03-09\n",
                   credits=("CR1,C1,I1,750,USD,DAMAGED,,2026-03-20\n"       # no approval above 500
                            "CR2,C1,I1,120,USD,,,2026-06-25\n"              # no reason code
                            "CR3,C1,I1,300,USD,LATE,,2026-07-20\n"          # fine
                            "CR4,C1,I1,2500,USD,GOODWILL,APP-9,2026-08-01\n"))  # approved but over max
    run(admin.org_id, date(2026, 10, 26))
    got = {f.evidence["credit"]["source_record_id"]: f.value for f in findings(session, admin.org_id)}
    assert got == {"CR1": D("750"), "CR2": D("120"), "CR4": D("500")}
    cr1 = next(f for f in findings(session, admin.org_id) if f.evidence["credit"]["source_record_id"] == "CR1")
    assert "without an approval reference" in cr1.reason and cr1.confidence == "high"


# ---------------------------------------------------------------- BE-019 idempotent runs and frozen findings

def test_rerun_never_duplicates_and_freezes_decided_findings(client, session):
    admin = _world(client, **UNBILLED)
    first = run(admin.org_id, date(2026, 6, 1))
    assert first.stats["new"] == 1
    second = run(admin.org_id, date(2026, 6, 1))
    assert (second.stats["new"], second.stats["unchanged"]) == (0, 1)
    [f] = findings(session, admin.org_id)
    assert f.first_run_id == first.id and f.last_run_id == second.id

    # Once proposed, later data changes must not move the value (decision 0003 D-2).
    session.execute(update(Finding).values(status="proposed"))
    session.commit()
    from tests.ingest_helpers import create_source, load
    load(client, admin, create_source(client, admin, "More"), "billable_event",
         EVENTS_HEAD + "E9,C1,A1,HOURS,5,hour,2026-04-20,2026-04-30,USD\n")
    third = run(admin.org_id, date(2026, 6, 1))
    assert third.stats["frozen"] == 1
    [f] = findings(session, admin.org_id)
    assert f.value == D("2160") and f.last_run_id == second.id


def test_finding_records_rule_version(client, session):
    admin = _world(client, **UNBILLED)
    client.put("/api/rules/delivered_not_billed", headers=admin.headers, json={"params": {"grace_days": 1}})
    run(admin.org_id, date(2026, 5, 3))
    [f] = findings(session, admin.org_id)
    rules = {r["check_type"]: r for r in client.get("/api/rules", headers=admin.headers).json()}
    assert str(f.rule_version_id) == rules["delivered_not_billed"]["active_version"]["id"]
    assert rules["delivered_not_billed"]["active_version"]["version_no"] == 2
