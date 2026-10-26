"""Connector interface (BE-009, FR-09). See README.md in this folder.

A connector fetches records from an external system and hands them to ingestion as CSV in the
canonical template columns. Ingestion then profiles and commits them exactly like a manual upload:
same validation, same idempotent upsert, same audit. A connector never touches assurance logic,
and never writes back to the external system (GR-01).
"""

from dataclasses import dataclass
from typing import Any, Protocol


class ConnectorError(Exception):
    """A problem whose message is safe to show to an administrator."""


@dataclass(frozen=True)
class ConnectorInfo:
    key: str
    label: str
    description: str
    is_demo: bool
    options: dict[str, list[str]]  # e.g. {"dataset": [...], "stage": [...]}


class Connector(Protocol):
    key: str
    is_demo: bool

    def info(self) -> ConnectorInfo: ...

    def validate_config(self, config: dict[str, Any]) -> dict[str, Any]:
        """Return the cleaned config, or raise ConnectorError."""
        ...

    def available(self, config: dict[str, Any], stage: str) -> list[str]:
        """Record types this connector can deliver for `stage`."""
        ...

    def fetch(self, config: dict[str, Any], stage: str, record_type: str) -> tuple[str, bytes]:
        """(filename, CSV bytes with canonical template headers) for one record type."""
        ...
