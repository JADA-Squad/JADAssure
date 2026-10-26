"""finding workflow: root cause category and terminal-state immutability trigger (BE-021, GR-13)

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-26
"""
from alembic import op
import sqlalchemy as sa

revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None

# A finding in a terminal state can't change its money, evidence, calculation or status, whatever
# code path tries (GR-13). Deletes (org data deletion, FR-41) are still allowed.
TRIGGER_FN = """
CREATE OR REPLACE FUNCTION finding_terminal_immutable() RETURNS trigger AS $$
BEGIN
  IF OLD.status IN ('rejected', 'recovered', 'closed_no_recovery') AND (
       NEW.status IS DISTINCT FROM OLD.status
    OR NEW.value IS DISTINCT FROM OLD.value
    OR NEW.currency IS DISTINCT FROM OLD.currency
    OR NEW.evidence IS DISTINCT FROM OLD.evidence
    OR NEW.calculation IS DISTINCT FROM OLD.calculation
  ) THEN
    RAISE EXCEPTION 'finding % is %, which is final; its value, evidence and status cannot change', OLD.id, OLD.status
      USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""


def upgrade() -> None:
    op.add_column('finding', sa.Column('root_cause_category', sa.String(length=40), nullable=True))
    op.execute(TRIGGER_FN)
    op.execute("CREATE TRIGGER finding_terminal_immutable BEFORE UPDATE ON finding "
               "FOR EACH ROW EXECUTE FUNCTION finding_terminal_immutable()")
    for table in ("investigation_event", "approval"):
        op.alter_column(table, "created_at", server_default=sa.text("clock_timestamp()"))


def downgrade() -> None:
    for table in ("investigation_event", "approval"):
        op.alter_column(table, "created_at", server_default=sa.text("now()"))
    op.execute("DROP TRIGGER IF EXISTS finding_terminal_immutable ON finding")
    op.execute("DROP FUNCTION IF EXISTS finding_terminal_immutable()")
    op.drop_column('finding', 'root_cause_category')
