# assistant

**Built:** BE-034. Status: Built, awaiting owner checkpoint. Decision 0009.

An agentic chat assistant. Claude runs a bounded tool-use loop on the user's behalf. Read tools
answer from live data. Write tools only **prepare** an action; the change happens when the same
user clicks Confirm (GR-17).

- `tools.py`: the tool registry. Each tool needs a capability, so the user's role decides what the
  assistant can do. Write tools have `prepare` (validate, describe) and `execute` (call the
  existing workflow/service code with the user's own context).
- `agent.py`: the loop (max 8 model calls per message), the system prompt, and availability (the
  org's audited Claude opt-in plus `ANTHROPIC_API_KEY`). Claude calls go through
  `ai.anthropic_provider.AnthropicProvider.converse`.
- `service.py`: conversations (one user's only), the transcript the panel shows, and
  confirm/cancel, which re-check role and record state at the moment of the click.
- `router.py`: `/api/assistant/status`, `/conversations`, `/conversations/{id}/messages`,
  `/actions/{id}/confirm`, `/actions/{id}/cancel`.
- Audit: `assistant.message` (counts only, no text), `assistant.action_prepared`,
  `assistant.action_confirmed|cancelled|failed`, plus the underlying action's own events.

## Scope
Agentic assistance on top of the existing domains. It may import them; the engine domains must
never import this package (test-enforced, D-7). Next: BE-035 investigation agent, BE-036 triage
agent, BE-037 onboarding agent.

## Task IDs
BE-034, BE-035, BE-036, BE-037

Read each task's exact Acceptance Criteria in `docs/jadassure-task-board.csv` before implementing. Don't infer them from this README.
