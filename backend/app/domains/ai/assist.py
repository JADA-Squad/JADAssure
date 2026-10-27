"""AI assistance beyond extraction (BE-031, FR-39, FR-40). Suggestions and summaries only (GR-02).

- Mapping suggestions: proposed column → field pairs for columns still unmapped. They are never
  applied automatically; the admin applies them and saves the mapping.
- Finding summaries: plain-language text stored in `finding.ai_summary`, labelled AI-generated in
  the UI. No calculation reads it (the engine domains can't import `ai`, test-enforced), and the
  terminal-state trigger doesn't protect it because it isn't evidence.
"""

import difflib
import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.domains.ingestion.parsing import normalize_header
from app.domains.ingestion.registry import RecordSpec


class MappingSuggestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    column: str = Field(max_length=200)
    field: str = Field(max_length=80)
    confidence: float = Field(ge=0, le=1)
    reason: str = Field(max_length=200)


class MappingSuggestions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    suggestions: list[MappingSuggestion] = Field(max_length=200)


def stub_mapping(columns: list[str], spec: RecordSpec, taken: set[str]) -> list[MappingSuggestion]:
    """Fuzzy header matching on names, synonyms and description words (offline)."""
    out: list[MappingSuggestion] = []
    used = set(taken)
    for col in columns:
        h = normalize_header(col)
        best, score = None, 0.0
        for f in spec.fields:
            if f.name in used:
                continue
            words = [f.name, *f.synonyms, *re.findall(r"[a-z]+", f.description.lower())[:6]]
            s = max(difflib.SequenceMatcher(None, h, normalize_header(w)).ratio() for w in words)
            if h and any(h in normalize_header(w) or normalize_header(w) in h for w in (f.name, *f.synonyms) if len(w) > 2):
                s = max(s, 0.8)
            if s > score:
                best, score = f, s
        if best is not None and score >= 0.6:
            out.append(MappingSuggestion(column=col, field=best.name, confidence=round(score, 2),
                                         reason=f"'{col}' resembles '{best.name}'"))
            used.add(best.name)
    return out


def stub_summary(facts: dict[str, Any]) -> str:
    """Deterministic plain-language restatement of what the engine already computed."""
    return (f"{facts['check_label']} for {facts['customer']}: {facts['reason']} "
            f"The calculated amount is {facts['value']} {facts['currency']} ({facts['confidence']} confidence). "
            f"Suggested next step: {facts['recommended_action']}")


def finding_facts(f: Any) -> dict[str, Any]:
    """Only what the finding already contains; no other records are sent anywhere."""
    labels = {"delivered_not_billed": "Unbilled delivery", "incorrect_rate": "Wrong contracted rate",
              "expired_discount": "Discount outside its terms", "missed_increase": "Missed price increase",
              "credit_outside_policy": "Credit outside policy"}
    return {
        "check_label": labels.get(f.check_type, f.check_type),
        "customer": ((f.evidence or {}).get("customer") or {}).get("name", "the customer"),
        "reason": f.reason, "value": f"{f.value:,.2f}", "currency": f.currency,
        "confidence": f.confidence, "recommended_action": f.recommended_action, "status": f.status,
    }
