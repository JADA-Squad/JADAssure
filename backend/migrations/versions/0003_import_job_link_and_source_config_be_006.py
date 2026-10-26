"""import job link and source config BE-006

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-26
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('data_source', sa.Column('config', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")))
    op.add_column('import_batch', sa.Column('job_id', sa.UUID(), nullable=True))
    op.create_foreign_key(op.f('fk_import_batch_job_id_job'), 'import_batch', 'job', ['job_id'], ['id'], ondelete='SET NULL')


def downgrade() -> None:
    op.drop_constraint(op.f('fk_import_batch_job_id_job'), 'import_batch', type_='foreignkey')
    op.drop_column('import_batch', 'job_id')
    op.drop_column('data_source', 'config')
