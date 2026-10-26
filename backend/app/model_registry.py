"""Imports every module that defines tables so Base.metadata is complete (Alembic, tests)."""

import app.core.models  # noqa: F401
