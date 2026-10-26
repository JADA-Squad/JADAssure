# findings

**Built (M2):** FE-003 (queue). **In progress:** FE-004. The detail page shows side-by-side
evidence, calculation, timeline and comments, verified in a browser. Workflow actions (assign,
propose, reject, approve) and the AI summary label arrive with BE-021 in M3.

- `FindingsPage.tsx`: seven filters kept in the URL, priority order, totals per currency, and
  Run checks now for roles with `run_checks`.
- `FindingDetailPage.tsx`: route `/findings/:id`.
- Money is formatted from decimal strings with BigInt, never via floats (`components/format.ts`).

## Scope
Findings queue, finding detail and workflow actions.

## Task IDs
FE-003, FE-004

Read each task's exact Acceptance Criteria in `docs/jadassure-task-board.csv` before implementing. Don't infer them from this README.
