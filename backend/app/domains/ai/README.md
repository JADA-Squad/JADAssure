# ai

**Built (M4–M5):** BE-028, BE-031. Status: Built, awaiting owner checkpoint.

- `provider.py`: `AIProvider` protocol and the strict `ProposedTerm` / `ExtractionResult` schema.
- `stub.py`: offline deterministic reader, the default (nothing leaves JADAssure, GR-08).
- `anthropic_provider.py`: Claude adapter (`anthropic` SDK 2.x, `claude-opus-5-5`, JSON-schema
  output, server-side fallbacks, refusal / max_tokens handling, document delimited as untrusted).
- `registry.py`: `provider_for(org.settings)`. "anthropic" applies only after an audited opt-in
  AND with `ANTHROPIC_API_KEY` set; otherwise the stub.
- `assist.py` + `router.py` (BE-031): `GET /api/imports/{id}/mapping-suggestions` (deterministic
  value evidence first, then the provider; output filtered to real unmapped columns and free
  fields; never applied) and `POST /api/findings/{id}/summary` (stored in `ai_summary`, labelled
  in the UI, audited, read by no calculation). Decision 0008.
- Proposals only (GR-02). `matching`, `rules`, `cases`, `recovery` and `reporting` must never
  import this package (test-enforced). Decision 0007.

## Scope
The AI provider interface, offline stub, optional Anthropic adapter, mapping suggestions and finding summaries. Proposals only (GR-02).

## Task IDs
BE-028, BE-031

Read each task's exact Acceptance Criteria in `docs/jadassure-task-board.csv` before implementing. Don't infer them from this README.
