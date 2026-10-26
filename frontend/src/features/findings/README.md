# findings

**Built:** FE-003 (queue, M2) and FE-004 (detail with workflow actions, M3). Verified in a
browser.

- `FindingsPage.tsx`: seven filters kept in the URL, priority order, totals, Run checks now.
- `FindingDetailPage.tsx` + `ActionsPanel.tsx`: next-step guidance, Take ownership / assign,
  propose (root-cause category + description), reject / send back / write off (reason
  required), approve. These are exactly the server's `available_actions`. Also the prepared
  correction with CSV/JSON export, the labelled AI-summary slot, evidence, calculation and
  timeline.
- Money is formatted from decimal strings with BigInt, never via floats (`components/format.ts`).

## Scope
Findings queue, finding detail and workflow actions.

## Task IDs
FE-003, FE-004

Read each task's exact Acceptance Criteria in `docs/jadassure-task-board.csv` before implementing. Don't infer them from this README.
