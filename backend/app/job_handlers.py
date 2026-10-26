"""Imports every module that registers job handlers, so the worker (and tests) know all job kinds."""

import app.domains.connectors.service  # noqa: F401,E402  (connector_sync)
import app.domains.ingestion.service  # noqa: F401,E402  (import_commit)
import app.domains.recovery.service  # noqa: F401,E402  (recovery_reconcile)
import app.domains.rules.engine  # noqa: F401,E402  (run_checks)
