# rules

**Built (M2):** BE-010, BE-012, BE-014..BE-019. Status: Built, awaiting owner checkpoint.

- `config.py`: typed, versioned rule parameters per org; business-type defaults (BE-012).
- `checks.py`: the five checks. Price checks evaluate a line once and value the total shortfall
  (decision 0003 D-1).
- `evidence.py`: JSON snapshots of the source records behind a finding (GR-16).
- `engine.py`: `evaluate()` (pure), `upsert_findings()` (fingerprint, frozen once proposed, D-2),
  `execute_run()`, the `run_checks` job, `enqueue_due()` for scheduled refresh (BE-010).
- API: `GET/PUT /api/rules`, `POST/GET /api/check-runs`.
- Expected demo findings are asserted in `tests/test_demo_findings.py` against
  `demo-data/README.md`.

## Scope
Versioned rule configurations, the five checks, finding generation and de-duplication, check runs and the refresh schedule. Must never import `ai`.

## Task IDs
BE-010, BE-012, BE-014, BE-015, BE-016, BE-017, BE-018, BE-019

Read each task's exact Acceptance Criteria in `docs/jadassure-task-board.csv` before implementing. Don't infer them from this README.
