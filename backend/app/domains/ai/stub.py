"""Offline, deterministic term extractor: the default provider (GR-08: nothing leaves JADAssure).

Pattern-based, for contract wording like the demo amendment:
    "<Role> rate: USD 195.00 per hour, effective 1 August 2026."
    "a discount of 5% applies to <scope>, effective 1 August 2026 until 31 December 2026."
It proposes only what it can anchor to a verbatim passage, and flags conditional or open
language ("subject to agreement", "to be confirmed", thresholds) as ambiguous. It never follows
instructions in the text. It only matches term patterns, so a line like "ignore all previous
instructions" simply isn't a term.
"""

import re
from datetime import date, datetime

from app.domains.ai.provider import ExtractionContext, ExtractionResult, ProposedTerm

_DATE = r"(\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4})"
_RATE = re.compile(
    r"(?P<role>[A-Z][A-Za-z ]{1,60}?) rate:\s*(?P<ccy>[A-Z]{3})\s*(?P<amt>\d{1,3}(?:,\d{3})*(?:\.\d+)?)\s*per\s*(?P<unit>[a-z]+)"
    r"(?P<rest>[^\n]*(?:\n(?!\s*\n)[^\n]*)*)"
)
_DISCOUNT = re.compile(r"discount of (?P<pct>\d+(?:\.\d+)?)%(?P<rest>[^\n]*(?:\n(?!\s*\n)[^\n]*)*)", re.IGNORECASE)
_EFFECTIVE_DOC = re.compile(r"(?:takes effect|effective)\s+on\s+" + _DATE, re.IGNORECASE)
_EFFECTIVE = re.compile(r"effective\s+" + _DATE, re.IGNORECASE)
_UNTIL = re.compile(r"until\s+" + _DATE, re.IGNORECASE)
_AMBIGUOUS = (
    ("subject to agreement", "Rate is subject to a further agreement between the parties"),
    ("to be confirmed", "Value is marked as to be confirmed"),
    ("to be agreed", "Value is marked as to be agreed"),
    ("subject to", "Term is conditional"),
    ("at the discretion", "Term is discretionary"),
)
_CONDITIONAL_DISCOUNT = re.compile(r"\babove\b|\bover\b|\bexceeding\b|\bmore than\b", re.IGNORECASE)


def _parse_date(s: str) -> date:
    return datetime.strptime(" ".join(s.split()), "%d %B %Y").date()


def _sentence(text: str, start: int, end: int) -> str:
    """The numbered clause / paragraph containing the match, verbatim (trimmed of outer whitespace)."""
    left = text.rfind("\n\n", 0, start)
    right = text.find("\n\n", end)
    chunk = text[left + 2 if left >= 0 else 0: right if right >= 0 else len(text)]
    return chunk.strip()


def _item_code(role: str, known: tuple[str, ...]) -> str | None:
    """Match 'Senior consultant' to SENIOR-CONSULT: every word must prefix a code part, in order."""
    words = [w.lower() for w in re.findall(r"[A-Za-z]+", role)]
    for code in known:
        parts = [p.lower() for p in re.split(r"[-_ ]", code) if p]
        if len(parts) == len(words) and all(p.startswith(w[: len(p)]) or w.startswith(p) for w, p in zip(words, parts)):
            return code
    return None


def _ambiguity(passage: str) -> str | None:
    low = passage.lower()
    for phrase, reason in _AMBIGUOUS:
        if phrase in low:
            return reason
    return None


class StubProvider:
    name = "stub"
    external = False

    def extract_terms(self, text: str, ctx: ExtractionContext) -> ExtractionResult:
        doc_effective = _EFFECTIVE_DOC.search(text)
        default_from = _parse_date(doc_effective.group(1)) if doc_effective else None
        terms: list[ProposedTerm] = []

        for m in _RATE.finditer(text):
            passage = _sentence(text, m.start(), m.end())
            eff = _EFFECTIVE.search(m.group("rest"))
            item = _item_code(m.group("role"), ctx.known_item_codes)
            reason = _ambiguity(passage) or (None if item else f"No known item matches '{m.group('role').strip()}'")
            terms.append(ProposedTerm(
                term_type="rate", item_code=item, value=m.group("amt").replace(",", ""), unit=m.group("unit"),
                currency=m.group("ccy"), effective_from=_parse_date(eff.group(1)) if eff else default_from,
                passage=passage, ambiguous=reason is not None, ambiguity_reason=reason,
            ))

        for m in _DISCOUNT.finditer(text):
            passage = _sentence(text, m.start(), m.end())
            rest = m.group("rest")
            eff, until = _EFFECTIVE.search(rest), _UNTIL.search(rest)
            reason = _ambiguity(passage)
            if reason is None and _CONDITIONAL_DISCOUNT.search(rest):
                reason = "Discount depends on a volume threshold the engine can't apply automatically"
            terms.append(ProposedTerm(
                term_type="discount", item_code=None, value=m.group("pct"), unit="pct", currency=None,
                effective_from=_parse_date(eff.group(1)) if eff else default_from,
                effective_to=_parse_date(until.group(1)) if until else None,
                passage=passage, ambiguous=reason is not None, ambiguity_reason=reason,
            ))
        return ExtractionResult(terms=terms)

    def suggest_mapping(self, columns, samples, spec, taken):
        from app.domains.ai.assist import stub_mapping

        return stub_mapping(columns, spec, taken)

    def summarize_finding(self, facts):
        from app.domains.ai.assist import stub_summary

        return stub_summary(facts)
