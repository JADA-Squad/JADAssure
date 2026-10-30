"""Decision 0010: OpenAI as a switchable provider behind the same interface and safeguards.

OpenAI is replaced by a scripted fake client, so these run offline and deterministically.
"""

import json
import uuid
from datetime import date
from types import SimpleNamespace

from openai.types.chat import ChatCompletion
from openai.types.responses import Response
from sqlalchemy import select

from app.core.config import get_settings
from app.domains.access.models import Organization
from app.domains.ai import openai_provider
from app.domains.ai.openai_provider import OpenAIProvider, to_responses_input
from app.domains.ai.provider import ExtractionContext
from app.domains.ai.registry import provider_for
from app.domains.ai.stub import StubProvider
from app.domains.rules.models import Finding
from app.seed_demo import main as seed
from tests.engine_helpers import run
from tests.factories import signup
from tests.test_recovery import _demo


def completion(content=None, tool_calls=None, finish="stop"):
    return ChatCompletion.model_validate({
        "id": "chatcmpl-test", "object": "chat.completion", "created": 0, "model": "gpt-test",
        "choices": [{"index": 0, "finish_reason": finish, "logprobs": None,
                     "message": {"role": "assistant", "content": content, "refusal": None,
                                 "tool_calls": tool_calls}}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}})


def response(text=None, calls=()):
    """A Responses API reply: optional text, then function calls."""
    output = []
    if text:
        output.append({"type": "message", "id": "msg_1", "role": "assistant", "status": "completed",
                       "content": [{"type": "output_text", "text": text, "annotations": []}]})
    for call_id, name, args in calls:
        output.append({"type": "function_call", "id": f"fc_{call_id}", "call_id": call_id, "name": name,
                       "arguments": json.dumps(args), "status": "completed"})
    return Response.model_validate({
        "id": "resp_test", "object": "response", "created_at": 0, "model": "gpt-test", "output": output,
        "status": "completed", "parallel_tool_calls": True, "tool_choice": "auto", "tools": [],
        "usage": {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2,
                  "input_tokens_details": {"cached_tokens": 0, "cache_write_tokens": 0}, "output_tokens_details": {"reasoning_tokens": 0}}})


class FakeOpenAI:
    """Stands in for openai.OpenAI(): records requests, replays scripted completions."""

    def __init__(self, *steps):
        self.steps = list(steps)
        self.requests = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))
        self.responses = SimpleNamespace(create=self._create)

    def _create(self, **params):
        self.requests.append(json.loads(json.dumps(params)))
        step = self.steps.pop(0)
        return step(params) if callable(step) else step


def test_history_translates_to_responses_items():
    history = [
        {"role": "user", "content": [{"type": "text", "text": "Find it"}]},
        {"role": "assistant", "content": [{"type": "text", "text": "Looking."},
                                          {"type": "tool_use", "id": "c1", "name": "list_findings", "input": {}}]},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "c1", "content": "[]", "is_error": True},
                                     {"type": "text", "text": "and then?"}]},
    ]
    out = to_responses_input(history)
    assert [i.get("type") or i["role"] for i in out] == ["user", "assistant", "function_call",
                                                         "function_call_output", "user"]
    assert out[2] == {"type": "function_call", "call_id": "c1", "name": "list_findings", "arguments": "{}"}
    assert out[3] == {"type": "function_call_output", "call_id": "c1", "output": "Error: []"}


def test_structured_extraction_and_errors():
    terms = {"terms": [{"term_type": "rate", "item_code": "SENIOR-CONSULT", "value": "195.00", "unit": "hour",
                        "currency": "USD", "effective_from": "2026-08-01", "effective_to": None,
                        "passage": "2.1 Senior consultant rate: USD 195.00 per hour", "ambiguous": False,
                        "ambiguity_reason": None}]}
    fake = FakeOpenAI(completion(json.dumps(terms)))
    result = OpenAIProvider(client=fake).extract_terms(
        "contract text", ExtractionContext(org_id=uuid.uuid4(), agreement_title="SOW", currency="USD",
                                           known_item_codes=("SENIOR-CONSULT",)))
    assert result.terms[0].value == "195.00"
    sent = fake.requests[0]
    assert sent["response_format"]["json_schema"]["strict"] is True
    assert "<document>" in sent["messages"][1]["content"] and "untrusted" in sent["messages"][0]["content"]


def test_choosing_openai_needs_its_own_key(client, monkeypatch):
    admin = signup(client)
    r = client.put("/api/settings", headers=admin.headers, json={"ai_provider": "openai"})
    assert r.status_code == 422 and "OPENAI_API_KEY" in r.json()["detail"]
    monkeypatch.setattr(get_settings(), "openai_api_key", "sk-test-not-real")
    monkeypatch.setattr(openai_provider.openai, "OpenAI", lambda **kw: FakeOpenAI())
    s = client.get("/api/settings", headers=admin.headers).json()
    assert s["ai_available_providers"] == ["openai"]
    r = client.put("/api/settings", headers=admin.headers, json={"ai_provider": "openai"})
    assert r.status_code == 200 and r.json()["ai_provider"] == "openai"
    assert isinstance(provider_for({"ai_provider": "openai"}), OpenAIProvider)
    assert "ai.external_provider_enabled" in [e["action"] for e in
                                               client.get("/api/audit", headers=admin.headers).json()]
    monkeypatch.setattr(get_settings(), "openai_api_key", "")
    assert isinstance(provider_for({"ai_provider": "openai"}), StubProvider)  # key removed → stub


def test_assistant_runs_on_openai_with_the_same_safeguards(client, session, monkeypatch):
    seed([])
    org = session.scalar(select(Organization).where(Organization.name == "JM"))
    run(org.id, date(2026, 10, 26))
    org.settings = {**(org.settings or {}), "ai_provider": "openai"}
    session.commit()
    monkeypatch.setattr(get_settings(), "openai_api_key", "sk-test-not-real")

    def propose(params):
        found = json.loads(params["input"][-1]["output"])["items"]
        return response(calls=[("call_2", "propose_finding", {
            "finding_id": found[0]["id"], "root_cause_category": "price_not_updated",
            "root_cause": "March price book entry was 40, not 45"})])

    fake = FakeOpenAI(response(calls=[("call_1", "list_findings", {"check_type": "incorrect_rate"})]),
                      propose,
                      response("Prepared. Please review and click Confirm."))
    monkeypatch.setattr(openai_provider.openai, "OpenAI", lambda **kw: fake)

    analyst = _demo(client, "analyst", "jm.com")
    assert client.get("/api/assistant/status", headers=analyst.headers).json()["available"] is True
    conv = client.post("/api/assistant/conversations", headers=analyst.headers).json()["id"]
    r = client.post(f"/api/assistant/conversations/{conv}/messages", headers=analyst.headers,
                    json={"text": "Propose the Bluefin wrong-rate finding"})
    assert r.status_code == 200, r.text
    assert [i["kind"] for i in r.json()["items"]] == ["user", "lookup", "action", "assistant"]
    tools_sent = {t["name"] for t in fake.requests[0]["tools"]}
    assert "propose_finding" in tools_sent and "approve_finding" not in tools_sent  # role-scoped (D-2)
    assert fake.requests[1]["input"][-1]["type"] == "function_call_output"
    assert fake.requests[0]["store"] is False and "JADAssure assistant" in fake.requests[0]["instructions"]

    session.expire_all()
    assert session.scalar(select(Finding).where(Finding.check_type == "incorrect_rate")).status == "open"  # GR-17
    action = r.json()["items"][2]["action"]
    assert client.post(f"/api/assistant/actions/{action['id']}/confirm",
                       headers=analyst.headers).json()["status"] == "confirmed"
    session.expire_all()
    assert session.scalar(select(Finding).where(Finding.check_type == "incorrect_rate")).status == "proposed"
