"""Seed the three DEMO organizations (DATA-001).

    docker compose exec api python -m app.seed_demo

Creates each demo org (flagged is_demo) with one user per role, a demonstration-connector data
source loaded with the dataset's baseline files, and an empty "Manual uploads" CSV source.
Idempotent: an org that already exists is left untouched.

All data is synthetic (demo-data/README.md). The shared DEMO_PASSWORD below exists only so local
demos can sign in. It's listed on the login page only when SHOW_DEMO_ACCOUNTS=true.
"""

import sys
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

import app.job_handlers  # noqa: F401
import app.model_registry  # noqa: F401
from app.core.db import new_session
from app.core.tenancy import TenantContext
from app.domains.access import service as access
from app.domains.access.models import Organization
from app.domains.audit import service as audit
from app.domains.connectors import service as connectors
from app.domains.ingestion import service as ingestion
from app.domains.rules import config as rules_config

DEMO_PASSWORD = "jadassure-demo-2026"


@dataclass(frozen=True)
class DemoOrg:
    dataset: str
    name: str
    business_type: str
    slug: str


DEMO_ORGS = (
    DemoOrg("northwind-advisory", "Northwind Advisory (demo)", "professional_services", "northwind"),
    DemoOrg("cirrus-cloud", "Cirrus Cloud (demo)", "subscription_software", "cirrus"),
    DemoOrg("ridgeline-supply", "Ridgeline Supply (demo)", "distribution", "ridgeline"),
)

DEMO_USERS = (
    ("admin", "Avery Admin"),
    ("analyst", "Ana Analyst"),
    ("approver", "Parker Approver"),
    ("commercial", "Cam Commercial"),
    ("executive", "Eden Executive"),
)


def demo_email(role: str, slug: str) -> str:
    return f"{role}.{slug}@example.com"


def seed_org(session: Session, spec: DemoOrg) -> str:
    if session.scalar(select(Organization).where(Organization.name == spec.name)):
        return f"{spec.name}: already present, skipped"
    org = access.create_organization(session, name=spec.name, business_type=spec.business_type, is_demo=True)
    audit.record(session, org_id=org.id, actor_id=None, action="organization.created", entity="organization",
                 entity_id=org.id, payload={"business_type": spec.business_type, "is_demo": True})
    users = {
        role: access.add_user(session, org_id=org.id, email=demo_email(role, spec.slug), name=f"{name} (demo)",
                              role=role, password=DEMO_PASSWORD, actor_id=None)
        for role, name in DEMO_USERS
    }
    ctx = TenantContext(user_id=users["admin"].id, org_id=org.id, role="admin")
    source = connectors.create_connector_source(session, ctx, name="Demo connector", connector_key="demo",
                                                config={"dataset": spec.dataset})
    ingestion.create_source(session, ctx, name="Manual uploads")
    rules_config.ensure_rules(session, org.id, spec.business_type, users["admin"].id)
    batches = connectors.run_sync(session, source, "baseline", users["admin"].id)
    loaded = sum(b.counts.get("inserted", 0) for b in batches)
    rejected = sum(b.counts.get("rejected", 0) for b in batches)
    if rejected:
        raise RuntimeError(f"{spec.dataset}: {rejected} demo rows were rejected; fix demo-data/generate.py")
    return f"{spec.name}: created ({org.short_code}), {len(users)} users, {loaded} records loaded"


def main() -> int:
    with new_session() as session:
        for spec in DEMO_ORGS:
            print(seed_org(session, spec))
            session.commit()
    print(f"Demo users: <role>.<org>@example.com (roles: {', '.join(r for r, _ in DEMO_USERS)}; "
          f"orgs: {', '.join(o.slug for o in DEMO_ORGS)}). Shared password is DEMO_PASSWORD in app/seed_demo.py.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
