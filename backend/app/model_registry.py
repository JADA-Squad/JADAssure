"""Imports every module that defines tables so Base.metadata is complete (Alembic, tests)."""

import app.core.models  # noqa: F401
import app.domains.access.models  # noqa: F401
import app.domains.audit.models  # noqa: F401
import app.domains.cases.models  # noqa: F401
import app.domains.contracts.models  # noqa: F401
import app.domains.ingestion.models  # noqa: F401
import app.domains.recovery.models  # noqa: F401
import app.domains.rules.models  # noqa: F401
