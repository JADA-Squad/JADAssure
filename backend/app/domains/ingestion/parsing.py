"""CSV reading and value conversion for imports. All content is untrusted data (GR-07)."""

import csv
import io
import re
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from app.domains.ingestion.registry import FieldSpec, RecordSpec

MAX_BYTES = 10 * 1024 * 1024
MAX_ROWS = 50_000

_DECIMAL = re.compile(r"^-?(\d{1,3}(,\d{3})+|\d+)(\.\d+)?$")
_INT = re.compile(r"^-?\d+$")
_CURRENCY = re.compile(r"^[A-Z]{3}$")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class CsvError(ValueError):
    """The file as a whole can't be read; the message is safe to show."""


def read_csv(data: bytes) -> tuple[list[str], list[dict[str, str]]]:
    if len(data) > MAX_BYTES:
        raise CsvError(f"File is larger than {MAX_BYTES // (1024 * 1024)} MB")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise CsvError("File must be UTF-8 encoded CSV") from None
    if "\x00" in text:
        raise CsvError("File looks binary, not CSV")
    reader = csv.reader(io.StringIO(text, newline=""))
    try:
        header = next(reader)
    except StopIteration:
        raise CsvError("File is empty") from None
    except csv.Error:
        raise CsvError("File is not valid CSV") from None
    headers = [h.strip() for h in header]
    if not any(headers):
        raise CsvError("Header row is empty")
    if len(set(headers)) != len(headers):
        raise CsvError("Header row has duplicate column names")
    rows: list[dict[str, str]] = []
    try:
        for raw in reader:
            if not any(cell.strip() for cell in raw):
                continue  # skip blank lines
            if len(rows) >= MAX_ROWS:
                raise CsvError(f"File has more than {MAX_ROWS} rows")
            rows.append({h: (raw[i].strip() if i < len(raw) else "") for i, h in enumerate(headers)})
    except csv.Error:
        raise CsvError(f"File is not valid CSV (problem near data row {len(rows) + 1})") from None
    return headers, rows


def normalize_header(h: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", h.lower()).strip("_")


def suggest_mapping(headers: list[str], spec: RecordSpec) -> dict[str, str]:
    """Deterministic header matching on names and synonyms. Suggestions only; the admin confirms."""
    lookup: dict[str, str] = {}
    for f in spec.fields:
        for alias in (f.name, *f.synonyms):
            lookup.setdefault(normalize_header(alias), f.name)
    mapping: dict[str, str] = {}
    used: set[str] = set()
    for h in headers:
        target = lookup.get(normalize_header(h))
        if target and target not in used:
            mapping[h] = target
            used.add(target)
    return mapping


def parse_value(spec: FieldSpec, raw: str) -> tuple[Any, str | None]:
    """Convert one raw cell. Returns (value, error). Empty cells return (None, None)."""
    raw = raw.strip()
    if raw == "":
        return None, None
    t = spec.type
    if t in ("id", "str", "ref"):
        if len(raw) > spec.max_length:
            return None, f"longer than {spec.max_length} characters"
        return raw, None
    if t == "decimal":
        if not _DECIMAL.match(raw):
            return None, "not a number"
        try:
            return Decimal(raw.replace(",", "")), None
        except InvalidOperation:
            return None, "not a number"
    if t == "int":
        return (int(raw), None) if _INT.match(raw) else (None, "not a whole number")
    if t == "date":
        if not _DATE.match(raw):
            return None, "not a date in YYYY-MM-DD format"
        try:
            return date.fromisoformat(raw), None
        except ValueError:
            return None, "not a valid date"
    if t == "currency":
        code = raw.upper()
        return (code, None) if _CURRENCY.match(code) else (None, "not a 3-letter currency code")
    if t == "enum":
        value = raw.lower()
        return (value, None) if value in spec.choices else (None, f"must be one of: {', '.join(spec.choices)}")
    raise AssertionError(f"unknown field type {t}")


def canonical_text(value: Any) -> str | None:
    """Stable text form of a converted value, used for change detection hashes."""
    if value is None:
        return None
    if isinstance(value, Decimal):
        text = format(value.normalize(), "f")
        return "0" if text in ("-0", "") else text
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def csv_safe(cell: str) -> str:
    """Neutralize spreadsheet formula injection in CSVs we generate (GR-07)."""
    return "'" + cell if cell.startswith(_FORMULA_PREFIXES) else cell
