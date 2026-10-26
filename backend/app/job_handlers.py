"""Imports every module that registers job handlers, so the worker (and tests) know all job kinds."""

import app.domains.ingestion.service  # noqa: F401,E402  (import_commit)
