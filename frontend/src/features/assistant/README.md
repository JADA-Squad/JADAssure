# assistant

**Built:** FE-010. Status: Built, awaiting owner checkpoint.

`AssistantPanel.tsx` is mounted once in the app layout, so an **Assistant** button sits on every
screen. The panel shows the conversation, a "Looked up …" line for each read, and a card for each
prepared action with **Confirm** and **Cancel** (financial decisions carry an extra warning).
Confirming refreshes every screen's data. When Claude isn't enabled for the org, the panel says
what's needed. Role-based starter questions help first-time users.

Verified in a browser (prepared-action card confirmed, overview refreshed). The full Claude loop
needs `ANTHROPIC_API_KEY` and the org's opt-in; it's covered by `backend/tests/test_assistant.py`.

## Scope
The assistant chat panel.

## Task IDs
FE-010

Read each task's exact Acceptance Criteria in `docs/jadassure-task-board.csv` before implementing. Don't infer them from this README.
