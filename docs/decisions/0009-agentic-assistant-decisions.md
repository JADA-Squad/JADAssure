# 0009 — Agentic assistant: prepared actions, human confirmation (BE-034, FE-010)

| | |
|---|---|
| Date | 2026-10-30 |
| Status | Accepted |
| Applies to | JADAssure |
| Adds | FR-43–FR-46, GR-17; new `assistant` backend domain and frontend feature |

**Context.** The owner asked for agentic AI, starting with a chat assistant that can take actions
for each user according to their role, while keeping the existing approach: AI proposes, people
decide, and money comes only from deterministic code (GR-02).

**D-1. The agent prepares; the user confirms; existing code executes.** Claude runs a tool-use
loop (look things up, reason, call more tools). Read tools return live data. Every tool that
would change something only creates an `assistant_action` row with status `proposed` and a plain
summary. Nothing changes until the same user clicks **Confirm**. The change then runs through the
same workflow and service functions as the screens (for example `cases.workflow.transition`),
inside one transaction with the audit events. A model output alone can never change data (GR-17).

**D-2. Role-scoped tool set, checked twice.** The model is only offered the tools whose capability
the user's role holds, so an analyst's assistant has no approve tool and an executive's has only
read tools. Preparing an action checks the capability and the record's state. Confirming checks
both again against the user's current token and the record's current state, so a stale or
tampered action fails safely. Separation of duties (GR-12) still applies: the approve tool fails
for the proposer exactly as the screen does.

**D-3. Only on the org's audited Claude opt-in.** The assistant needs a model that can plan and
call tools; the offline stub can't. It is available only when the org's admin has chosen Claude in
Access & settings and the server has `ANTHROPIC_API_KEY` (GR-08). Otherwise the panel explains
what's needed. All Claude calls stay in the `ai` domain (`AnthropicProvider.converse`).

**D-4. Untrusted data stays data (GR-07).** Tool results include imported names, comments and
contract passages. The system prompt declares them untrusted, and D-1 means an injected
instruction can at most cause a *proposed* action that the user sees, reads and can cancel.

**D-5. Isolation and privacy.** Conversations and actions belong to one user in one org
(`org_id` from the token, plus `user_id`); others get 404. The audit log records that a message
was sent, how many tools ran and each action prepared, confirmed or cancelled, but not the chat
text (GR-15). The transcript itself is stored for the user in `assistant_conversation`.

**D-6. Bounded cost and behaviour.** At most 8 model calls per user message, 4,000 output tokens
per call, 4,000 characters per message, and 60 stored messages per conversation (then start a
new one). Tool results are truncated to keep requests small.

**D-7. Engine boundary extended.** The engine domains (`matching`, `rules`, `cases`, `recovery`,
`reporting`) must not import `ai` or `assistant`. The `assistant` domain may import them, because
it only calls their existing functions on the user's behalf.

**D-8. Order of the agentic roadmap.** BE-034/FE-010 (chat assistant) first. Then BE-035
(investigation agent), BE-036 (triage after check runs) and BE-037 (onboarding agent for the FDE),
each built on the same prepared-action pattern.
