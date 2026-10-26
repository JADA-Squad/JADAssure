# ai

**Built (M4):** BE-028. Status: Built, awaiting owner checkpoint. BE-031 (mapping
suggestions, finding summaries) is Backlog for M5.

- `provider.py`: `AIProvider` protocol and the strict `ProposedTerm` / `ExtractionResult` schema.
- `stub.py`: offline deterministic reader, the default (nothing leaves JADAssure, GR-08).
- `anthropic_provider.py`: Claude adapter (`anthropic` SDK 2.x, `claude-opus-5-5`, JSON-schema
  output, server-side fallbacks, refusal / max_tokens handling, document delimited as untrusted).
- `registry.py`: `provider_for(org.settings)`. "anthropic" applies only after an audited opt-in
  AND with `ANTHROPIC_API_KEY` set; otherwise the stub.
- Proposals only (GR-02). `matching`, `rules`, `cases`, `recovery` and `reporting` must never
  import this package (test-enforced). Decision 0007.

## Scope
The AI provider interface, offline stub, optional Anthropic adapter, mapping suggestions and finding summaries. Proposals only (GR-02).

## Task IDs
BE-028, BE-031

Read each task's exact Acceptance Criteria in `docs/jadassure-task-board.csv` before implementing. Don't infer them from this README.
