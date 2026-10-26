"""Document store behind an interface, local filesystem for the pilot (decision 0001 D-4).

Holds uploaded import files, error reports and (from BE-027) contract documents. Swapping to
S3/Azure later means adding one class with the same three methods.
"""

import pathlib
import re
import shutil
import uuid
from functools import lru_cache
from typing import Protocol

from app.core.config import get_settings

_SAFE_PART = re.compile(r"^[A-Za-z0-9_.-]+$")


class DocumentStore(Protocol):
    def put(self, org_id: uuid.UUID, namespace: str, data: bytes, suffix: str = "") -> str: ...
    def get(self, key: str) -> bytes: ...
    def delete(self, key: str) -> None: ...
    def delete_org(self, org_id: uuid.UUID) -> int: ...


class LocalDocumentStore:
    def __init__(self, root: str):
        self.root = pathlib.Path(root).resolve()

    def _path(self, key: str) -> pathlib.Path:
        parts = key.split("/")
        if len(parts) != 3 or not all(_SAFE_PART.match(p) and p not in (".", "..") for p in parts):
            raise ValueError("invalid storage key")
        path = (self.root / key).resolve()
        if self.root not in path.parents:
            raise ValueError("invalid storage key")
        return path

    def put(self, org_id: uuid.UUID, namespace: str, data: bytes, suffix: str = "") -> str:
        if not _SAFE_PART.match(namespace) or (suffix and not _SAFE_PART.match(suffix)):
            raise ValueError("invalid namespace or suffix")
        key = f"{org_id}/{namespace}/{uuid.uuid4().hex}{suffix}"
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return key

    def get(self, key: str) -> bytes:
        if key == "purged":  # removed by retention (access.settings.purge_expired_files)
            raise FileNotFoundError(key)
        return self._path(key).read_bytes()

    def delete(self, key: str) -> None:
        if key != "purged":
            self._path(key).unlink(missing_ok=True)

    def delete_org(self, org_id: uuid.UUID) -> int:
        """Remove every stored file of an organization (FR-41). Returns the number of files removed."""
        folder = (self.root / str(org_id)).resolve()
        if self.root not in folder.parents or not folder.is_dir():
            return 0
        count = sum(1 for p in folder.rglob("*") if p.is_file())
        shutil.rmtree(folder)
        return count


_override: DocumentStore | None = None


def set_store(store: DocumentStore | None) -> None:
    """Swap the store (tests use a temporary directory)."""
    global _override
    _override = store


@lru_cache
def _default_store() -> DocumentStore:
    return LocalDocumentStore(get_settings().document_store_path)


def get_store() -> DocumentStore:
    return _override or _default_store()
