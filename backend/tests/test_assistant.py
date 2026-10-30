"""BE-034: the agentic assistant prepares actions; only the user's confirmation changes data (FR-43, GR-17).

Claude is replaced by a scripted provider, so these run offline and deterministically.
"""

import json
from datetime import date

import pytest
from anthropic.types.beta import BetaMessage
from sqlalchemy import select

from app.core.config import get_settings
from app.domains.access.models import Organization
from app.domains.assistant import agent
from app.domains.assistant.agent import NOTE_PREFIX
from app.domains.rules.models import Finding
from app.seed_demo import main as seed
from tests.engine_helpers import run
from tests.test_recovery import _demo


def msg(*content, stop="end_turn"):
    return BetaMessage.model_validate({
        "id": "msg_test", "type": "message", "role": "assistant", "model": "claude-opus-5-5", "content": list(content),
        "stop_reason": stop, "stop_sequence": None, "usage": {"input_tokens": 1, "output_tokens": 1}})


def text(t):
    return {"type": "text", "text": t}


def use(tool_id, name, **args):
    return {"type": "tool_use", "id": tool_id, "name": name, "input": args}


def last_result(messages):
    """The JSON of the most recent tool result the agent sent back."""
    block = messages[-1]["content"][-1]
    assert block["type"] == "tool_result"
    return block


class Scripted:
    """Stands in for Claude: each step is a message, or a function of the messages so far."""

    def __init__(self, *steps):
        self.steps = list(steps)
        self.calls = []

    def converse(self, system, messages, tools, max_tokens=4000):
        self.calls.append({"system": system, "messages": json.loads(json.dumps(messages)),
                           "tools": [t["name"] for t in tools]})
        step = self.steps.pop(0)
        return step(messages) if callable(step) else step


@pytest.fixture
def jm(client, session, monkeypatch):
    seed([])
    org = session.scalar(select(Organization).where(Organization.name == "JM"))
    run(org.id, date(2026, 10, 26))
    monkeypatch.setattr(get_settings(), "anthropic_api_key", "sk-test-not-real")
    org.settings = {**(org.settings or {}), "ai_provider": "anthropic"}
    session.commit()
    return org


def use_provider(monkeypatch, provider):
    monkeypatch.setattr(agent, "make_provider", lambda org: provider)


def chat(client, actor, text_, conv=None):
    conv = conv or client.post("/api/assistant/conversations", headers=actor.headers).json()["id"]
    r = client.post(f"/api/assistant/conversations/{conv}/messages", headers=actor.headers, json={"text": text_})
    return conv, r


def finding(session, check_type):
    session.expire_all()
    return session.scalar(select(Finding).where(Finding.check_type == check_type))


def test_unavailable_until_claude_is_enabled(client, session, monkeypatch):
    seed([])
    analyst = _demo(client, "analyst", "jm.com")
    st = client.get("/api/assistant/status", headers=analyst.headers).json()  # no key on the server
    assert st["available"] is False and "add an API key" in st["reason"]
    _, r = chat(client, analyst, "hello")
    assert r.status_code == 409
    monkeypatch.setattr(get_settings(), "openai_api_key", "sk-test-not-real")  # key, but the org hasn't opted in
    st = client.get("/api/assistant/status", headers=analyst.headers).json()
    assert st["available"] is False and "AI provider" in st["reason"]


def test_tools_follow_the_role(client, jm):
    status = {r: client.get("/api/assistant/status", headers=_demo(client, r, "jm.com").headers).json()
              for r in ("analyst", "approver", "executive", "admin")}
    assert status["analyst"]["available"] is True
    assert "propose_finding" in status["analyst"]["can_change"] and "approve_finding" not in status["analyst"]["can_change"]
    assert "approve_finding" in status["approver"]["can_change"] and "propose_finding" not in status["approver"]["can_change"]
    assert status["executive"]["can_change"] == [] and "get_outcomes" in status["executive"]["can_look_up"]
    assert "list_findings" not in status["admin"]["can_look_up"]  # admins don't touch findings


def test_agent_prepares_then_the_user_confirms(client, session, jm, monkeypatch):
    analyst = _demo(client, "analyst", "jm.com")
    rate = finding(session, "incorrect_rate")

    def propose_from_lookup(messages):
        items = json.loads(last_result(messages)["content"])["items"]
        return msg(use("t2", "propose_finding", finding_id=items[0]["id"], root_cause_category="price_not_updated",
                       root_cause="March price book entry was 40 instead of 45"), stop="tool_use")

    provider = Scripted(msg(use("t1", "list_findings", check_type="incorrect_rate"), stop="tool_use"),
                        propose_from_lookup,
                        msg(text("I've prepared the proposal. Please review and click Confirm.")))
    use_provider(monkeypatch, provider)
    conv, r = chat(client, analyst, "Propose the Bluefin wrong-rate finding; the price book wasn't updated.")
    assert r.status_code == 200, r.text
    kinds = [i["kind"] for i in r.json()["items"]]
    assert kinds == ["user", "lookup", "action", "assistant"]
    action = r.json()["items"][2]["action"]
    assert action["status"] == "proposed" and "600.00 USD" in action["summary"]
    assert "Finance analyst" in provider.calls[0]["system"]
    assert "approve_finding" not in provider.calls[0]["tools"]
    assert finding(session, "incorrect_rate").status == "open"  # nothing changed yet (GR-17)

    # Someone else can't confirm it, and nor can another org.
    approver = _demo(client, "approver", "jm.com")
    assert client.post(f"/api/assistant/actions/{action['id']}/confirm", headers=approver.headers).status_code == 404
    beyon = _demo(client, "analyst", "beyon.com")
    assert client.get(f"/api/assistant/conversations/{conv}", headers=beyon.headers).status_code == 404

    done = client.post(f"/api/assistant/actions/{action['id']}/confirm", headers=analyst.headers).json()
    assert done["status"] == "confirmed"
    f = finding(session, "incorrect_rate")
    assert (f.status, f.root_cause_category, str(f.proposer_id)) == ("proposed", "price_not_updated", analyst.user_id)
    assert f.id == rate.id
    assert client.post(f"/api/assistant/actions/{action['id']}/confirm", headers=analyst.headers).status_code == 409

    # The model learns the outcome with the next message; the note is hidden from the transcript.
    provider.steps.append(msg(text("It's now waiting for an approver.")))
    _, r = chat(client, analyst, "Thanks", conv)
    sent = provider.calls[-1]["messages"][-1]["content"]
    assert sent[0]["text"].startswith(NOTE_PREFIX) and "was confirmed" in sent[0]["text"]
    assert all(NOTE_PREFIX not in (i.get("text") or "") for i in r.json()["items"])

    actions = {e["action"] for e in client.get("/api/audit", headers=_demo(client, "admin", "jm.com").headers).json()}
    assert {"assistant.message", "assistant.action_prepared", "assistant.action_confirmed", "finding.propose"} <= actions


def test_role_and_state_are_rechecked_at_confirmation(client, session, jm, monkeypatch):
    analyst, approver = _demo(client, "analyst", "jm.com"), _demo(client, "approver", "jm.com")
    fid = str(finding(session, "incorrect_rate").id)
    client.post(f"/api/findings/{fid}/assign", headers=analyst.headers, json={"owner_id": analyst.user_id})
    client.post(f"/api/findings/{fid}/propose", headers=analyst.headers,
                json={"root_cause_category": "price_not_updated", "root_cause": "x"})

    # An analyst's model calling a tool it wasn't given gets an error, not an action.
    use_provider(monkeypatch, Scripted(msg(use("t1", "approve_finding", finding_id=fid), stop="tool_use"),
                                       msg(text("I can't approve; an approver must."))))
    _, r = chat(client, analyst, "approve it")
    assert [i["kind"] for i in r.json()["items"]] == ["user", "lookup", "assistant"]

    # The approver's prepared approval fails safely if the finding moved on before the click.
    use_provider(monkeypatch, Scripted(msg(use("t1", "approve_finding", finding_id=fid), stop="tool_use"),
                                       msg(text("Prepared."))))
    _, r = chat(client, approver, "approve the Bluefin finding")
    action = next(i["action"] for i in r.json()["items"] if i["kind"] == "action")
    assert client.post(f"/api/findings/{fid}/send-back", headers=approver.headers, json={"note": "check"}).status_code == 200
    failed = client.post(f"/api/assistant/actions/{action['id']}/confirm", headers=approver.headers).json()
    assert failed["status"] == "failed" and "in_review" in failed["result"]
    assert finding(session, "incorrect_rate").status == "in_review"


def test_cancel_changes_nothing(client, session, jm, monkeypatch):
    analyst = _demo(client, "analyst", "jm.com")
    fid = str(finding(session, "incorrect_rate").id)
    use_provider(monkeypatch, Scripted(msg(use("t1", "reject_finding", finding_id=fid, note="not leakage"),
                                           stop="tool_use"), msg(text("Prepared."))))
    _, r = chat(client, analyst, "reject it")
    action = next(i["action"] for i in r.json()["items"] if i["kind"] == "action")
    assert client.post(f"/api/assistant/actions/{action['id']}/cancel", headers=analyst.headers).json()["status"] == "cancelled"
    assert finding(session, "incorrect_rate").status == "open"


def test_executive_gets_answers_from_live_figures(client, jm, monkeypatch):
    executive = _demo(client, "executive", "jm.com")

    def answer(messages):
        figures = json.loads(last_result(messages)["content"])
        usd = next(c for c in figures["currencies"] if c["currency"] == "USD")
        return msg(text(f"Potential leakage is {usd['potential']} USD."))

    use_provider(monkeypatch, Scripted(msg(use("t1", "get_outcomes"), stop="tool_use"), answer))
    _, r = chat(client, executive, "How much leakage have we found?")
    assert r.json()["items"][-1]["text"].startswith("Potential leakage is 4530")
