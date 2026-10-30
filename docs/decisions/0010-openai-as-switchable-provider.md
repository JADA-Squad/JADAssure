# 0010 — OpenAI as a switchable AI provider (BE-038)

| | |
|---|---|
| Date | 2026-10-30 |
| Status | Accepted |
| Applies to | JADAssure |
| Amends | AGENTS.md §5 (AI provider row), decision 0007 D-3, decision 0009 D-3 |

**Context.** The owner's Anthropic key was rejected (not scoped to a workspace) and they have an
OpenAI key. They asked to switch to OpenAI now, keep the Anthropic structure, and keep the choice
switchable.

**D-1. Three providers, chosen per organization.** `ai_provider` is `stub` (offline, default),
`anthropic` (Claude) or `openai`. An external provider applies only when the org's admin chose it
(audited as `ai.external_provider_enabled`) and the server holds that provider's key
(`ANTHROPIC_API_KEY` / `OPENAI_API_KEY`). Otherwise the org falls back to the stub (GR-08).
Settings lists which providers are configured on the server.

**D-2. Same interface, same safeguards.** `OpenAIProvider` implements every `AIProvider` method:
term extraction and mapping suggestions use OpenAI structured outputs (`json_schema`, strict) and
are validated again locally; summaries are plain text. Untrusted input is delimited and declared as
data, exactly as for Claude. All results remain proposals (GR-02).

**D-3. The assistant keeps its message structure.** The agent loop, stored history and tools stay
in the Claude-style block format from decision 0009. `OpenAIProvider.converse` translates the
history and tool definitions into Responses API items and the reply back into the same blocks
(`tool_use`, `stop_reason`). It uses the **Responses API** (`store=False`), because some current
reasoning models (e.g. `gpt-6.1-sol`) refuse function tools on Chat Completions; the structured
calls (terms, mappings, summaries) use Chat Completions with a strict JSON schema. Switching provider
changes nothing else: role-scoped tools, prepared
actions and confirm-to-execute (GR-17) are identical.

**D-4. Model by configuration.** `OPENAI_MODEL` (default `gpt-4.1`) and `ANTHROPIC_MODEL` (default
`claude-opus-5-5`) are server settings, so a model can change without code.

**D-5. Tests never call a real model.** An autouse fixture blanks both keys in every test; tests
that need a provider set a fake key and a scripted client.
