"""AI provider interface (BE-028, decision 0001 D-2). Proposals only (GR-02).

Providers turn untrusted document text into *proposed* terms. Nothing a provider returns is
trusted: the caller (contracts.extraction) schema-validates every item, checks that its passage is
a verbatim substring of the document, and stores survivors as `proposed`. The engine domains can't
import this package (enforced by test), so AI output can never set a money figure.
"""

import uuid
from dataclasses import dataclass
from datetime import date
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

TermType = Literal["rate", "discount", "escalation", "credit_policy", "minimum"]


class ProposedTerm(BaseModel):
    """One commercial term as a provider proposes it. Strict: unknown fields are rejected."""

    model_config = ConfigDict(extra="forbid")

    term_type: TermType
    item_code: str | None = Field(default=None, max_length=80)
    value: str = Field(max_length=40, description="Decimal as text, e.g. '195.00' or '5'")
    unit: str | None = Field(default=None, max_length=40)
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    effective_from: date | None = None
    effective_to: date | None = None
    passage: str = Field(min_length=1, max_length=2000, description="Exact text copied from the document")
    ambiguous: bool = False
    ambiguity_reason: str | None = Field(default=None, max_length=500)


class ExtractionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    terms: list[ProposedTerm] = Field(max_length=100)


@dataclass(frozen=True)
class ExtractionContext:
    """What the provider may know besides the document: never other orgs' data."""

    org_id: uuid.UUID
    agreement_title: str
    currency: str
    known_item_codes: tuple[str, ...]


class ProviderError(Exception):
    """A provider failure whose message is safe to show (no document content)."""


class AIProvider(Protocol):
    name: str
    external: bool  # True if document text leaves JADAssure (GR-08)

    def extract_terms(self, text: str, ctx: ExtractionContext) -> ExtractionResult: ...

    def suggest_mapping(self, columns: list[str], samples: dict[str, list[str]], spec: Any,
                        taken: set[str]) -> list[Any]:
        """Proposed column -> field pairs (ai.assist.MappingSuggestion) for unmapped columns. Never applied."""
        ...

    def summarize_finding(self, facts: dict[str, Any]) -> str:
        """Plain-language summary of a finding's existing facts. Never used in calculations."""
        ...
