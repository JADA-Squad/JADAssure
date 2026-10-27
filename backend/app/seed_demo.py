"""Seed the two DEMO organizations, JM and Beyon (DATA-001, decision 0005).

    docker compose exec api python -m app.seed_demo [--remove-obsolete] [--reset JM [--reset Beyon]]

Each demo org (flagged is_demo) gets one user per role, one demonstration-connector data source
per dataset loaded with that dataset's baseline files, and an empty "Manual uploads" CSV source.
JM carries the professional-services and subscription-software datasets; Beyon carries
distribution. Together they still cover all three business types (FR-42).

Idempotent: an org that already exists is left as is, except that its demo users' passwords are
reset to DEMO_PASSWORD if that constant changed. With --remove-obsolete, demo-flagged
orgs that are no longer in DEMO_ORGS (e.g. demo orgs from earlier seeds) are
deleted first. With --reset <name>, that demo org is deleted and seeded again from scratch, e.g.
before a presentation. Orgs that aren't flagged is_demo are never touched.

All data is synthetic (demo-data/README.md). The shared DEMO_PASSWORD below exists only so demos
can sign in. It's listed on the login page only when SHOW_DEMO_ACCOUNTS=true.
"""

import sys
from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

import app.job_handlers  # noqa: F401
import app.model_registry  # noqa: F401
from app.core.db import new_session
from app.core.tenancy import TenantContext
from app.domains.access import service as access
from app.core.security import hash_password, verify_password
from app.domains.access.models import Organization, User
from app.domains.audit import service as audit
from app.domains.audit.models import AuditEvent
from app.domains.connectors import service as connectors
from app.domains.ingestion import service as ingestion
from app.domains.rules import config as rules_config

DEMO_PASSWORD = "Password!23"


@dataclass(frozen=True)
class DemoDataset:
    folder: str  # demo-data/<folder>
    source_name: str


@dataclass(frozen=True)
class DemoOrg:
    name: str
    business_type: str
    domain: str
    datasets: tuple[DemoDataset, ...]


DEMO_ORGS = (
    DemoOrg("JM", "professional_services", "jm.com", (
        DemoDataset("jm-advisory", "Demo connector: advisory services"),
        DemoDataset("jm-subscriptions", "Demo connector: platform subscriptions"),
    )),
    DemoOrg("Beyon", "distribution", "beyon.com", (
        DemoDataset("beyon-distribution", "Demo connector: distribution"),
    )),
)

# role -> (email local part, display name)
DEMO_USERS = {
    "admin": ("admin", "Avery Admin"),
    "analyst": ("financeanalyst", "Ana Analyst"),
    "approver": ("financeapprover", "Parker Approver"),
    "commercial": ("commercialmanager", "Cam Commercial"),
    "executive": ("executive", "Eden Executive"),
}


def demo_email(role: str, domain: str) -> str:
    """e.g. demo_email("analyst", "jm.com") == "financeanalyst@jm.com"."""
    return f"{DEMO_USERS[role][0]}@{domain}"


def _delete_demo_org(session: Session, org: Organization) -> None:
    # audit_event deliberately has no cascade (FR-41 tombstones); synthetic demo history goes too.
    session.execute(delete(AuditEvent).where(AuditEvent.org_id == org.id))
    session.delete(org)  # every other tenant table cascades on org_id


def remove_obsolete_demo_orgs(session: Session) -> list[str]:
    """Delete demo-flagged orgs that are no longer part of DEMO_ORGS. Never touches non-demo orgs."""
    current = {o.name for o in DEMO_ORGS}
    obsolete = [o for o in session.scalars(select(Organization).where(Organization.is_demo.is_(True)))
                if o.name not in current]
    for org in obsolete:
        _delete_demo_org(session, org)
    session.flush()
    return [o.name for o in obsolete]


def reset_demo_orgs(session: Session, names: list[str]) -> list[str]:
    """Delete the named demo orgs so they are seeded fresh. Refuses unknown or non-demo orgs."""
    known = {o.name for o in DEMO_ORGS}
    unknown = [n for n in names if n not in known]
    if unknown:
        raise SystemExit(f"--reset accepts only demo orgs ({', '.join(sorted(known))}), not: {', '.join(unknown)}")
    removed = []
    for org in session.scalars(select(Organization).where(Organization.name.in_(names))):
        if not org.is_demo:
            raise SystemExit(f"{org.name} is not flagged as demo; refusing to reset it")
        _delete_demo_org(session, org)
        removed.append(org.name)
    session.flush()
    return removed


def sync_demo_passwords(session: Session, org: Organization) -> int:
    """Reset users of a demo-flagged org to DEMO_PASSWORD if it changed. Never touches non-demo orgs."""
    if not org.is_demo:
        return 0
    changed = 0
    for user in session.scalars(select(User).where(User.org_id == org.id)):
        if not verify_password(DEMO_PASSWORD, user.password_hash):
            user.password_hash = hash_password(DEMO_PASSWORD)
            changed += 1
    if changed:
        audit.record(session, org_id=org.id, actor_id=None, action="demo.passwords_reset", entity="organization",
                     entity_id=org.id, payload={"users": changed})
    return changed


def seed_org(session: Session, spec: DemoOrg) -> str:
    existing = session.scalar(select(Organization).where(Organization.name == spec.name))
    if existing:
        changed = sync_demo_passwords(session, existing)
        return f"{spec.name}: already present" + (f", {changed} demo passwords updated" if changed else ", skipped")
    org = access.create_organization(session, name=spec.name, business_type=spec.business_type, is_demo=True)
    audit.record(session, org_id=org.id, actor_id=None, action="organization.created", entity="organization",
                 entity_id=org.id, payload={"business_type": spec.business_type, "is_demo": True})
    users = {
        role: access.add_user(session, org_id=org.id, email=demo_email(role, spec.domain), name=f"{name} (demo)",
                              role=role, password=DEMO_PASSWORD, actor_id=None)
        for role, (_, name) in DEMO_USERS.items()
    }
    ctx = TenantContext(user_id=users["admin"].id, org_id=org.id, role="admin")
    ingestion.create_source(session, ctx, name="Manual uploads")
    rules_config.ensure_rules(session, org.id, spec.business_type, users["admin"].id)
    loaded = rejected = 0
    for dataset in spec.datasets:
        source = connectors.create_connector_source(session, ctx, name=dataset.source_name, connector_key="demo",
                                                    config={"dataset": dataset.folder})
        batches = connectors.run_sync(session, source, "baseline", users["admin"].id)
        loaded += sum(b.counts.get("inserted", 0) for b in batches)
        rejected += sum(b.counts.get("rejected", 0) for b in batches)
    if rejected:
        raise RuntimeError(f"{spec.name}: {rejected} demo rows were rejected; fix demo-data/generate.py")
    return f"{spec.name}: created ({org.short_code}), {len(users)} users, {loaded} records loaded"


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    resets = [args[i + 1] for i, a in enumerate(args[:-1]) if a == "--reset"]
    with new_session() as session:
        if resets:
            reset = reset_demo_orgs(session, resets)
            session.commit()
            print(f"Reset demo orgs: {', '.join(reset) or 'none present'}")
        if "--remove-obsolete" in args:
            removed = remove_obsolete_demo_orgs(session)
            session.commit()
            if removed:
                print(f"Removed obsolete demo orgs: {', '.join(removed)}")
        for spec in DEMO_ORGS:
            print(seed_org(session, spec))
            session.commit()
    print("Demo users: " + ", ".join(f"{local}@<org domain>" for local, _ in DEMO_USERS.values())
          + f" for {', '.join(o.domain for o in DEMO_ORGS)}. Shared password is DEMO_PASSWORD in app/seed_demo.py.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
