"""Demonstration connector: serves synthetic files from demo-data/ (GR-14: always labelled demo)."""

import pathlib
import re
from typing import Any

from app.core.config import get_settings
from app.domains.connectors.base import ConnectorError, ConnectorInfo
from app.domains.ingestion.registry import LOAD_ORDER

_SAFE = re.compile(r"^[a-z0-9-]+$")
_NOT_STAGES = {"contracts", "manual"}


class DemoConnector:
    key = "demo"
    is_demo = True

    @property
    def root(self) -> pathlib.Path:
        return pathlib.Path(get_settings().demo_data_path)

    def _datasets(self) -> list[str]:
        if not self.root.is_dir():
            return []
        return sorted(p.name for p in self.root.iterdir() if p.is_dir() and _SAFE.match(p.name))

    def _stages(self, dataset: str) -> list[str]:
        base = self.root / dataset
        return sorted(p.name for p in base.iterdir() if p.is_dir() and p.name not in _NOT_STAGES and _SAFE.match(p.name))

    def info(self) -> ConnectorInfo:
        return ConnectorInfo(
            key=self.key,
            label="Demonstration connector (DEMO)",
            description="Loads synthetic demo files. Not a live customer integration.",
            is_demo=True,
            options={"dataset": self._datasets()},
        )

    def validate_config(self, config: dict[str, Any]) -> dict[str, Any]:
        dataset = config.get("dataset")
        if dataset not in self._datasets():
            raise ConnectorError(f"Unknown demo dataset. Available: {', '.join(self._datasets()) or 'none'}")
        return {"dataset": dataset}

    def _folder(self, config: dict[str, Any], stage: str) -> pathlib.Path:
        dataset = self.validate_config(config)["dataset"]
        if stage not in self._stages(dataset):
            raise ConnectorError(f"Unknown stage '{stage}'. Available: {', '.join(self._stages(dataset))}")
        return self.root / dataset / stage

    def available(self, config: dict[str, Any], stage: str) -> list[str]:
        folder = self._folder(config, stage)
        return [rt for rt in LOAD_ORDER if (folder / f"{rt}.csv").is_file()]

    def fetch(self, config: dict[str, Any], stage: str, record_type: str) -> tuple[str, bytes]:
        if record_type not in LOAD_ORDER:
            raise ConnectorError("Unknown record type")
        path = self._folder(config, stage) / f"{record_type}.csv"
        if not path.is_file():
            raise ConnectorError(f"No {record_type} file in this stage")
        return f"demo-{config['dataset']}-{stage}-{record_type}.csv", path.read_bytes()
