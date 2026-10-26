"""contract documents BE-027

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-26
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0005'
down_revision = '0004'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('document', sa.Column('agreement_id', sa.UUID(), nullable=True))
    op.add_column('document', sa.Column('extraction_status', sa.String(length=20), nullable=False, server_default='succeeded'))
    op.add_column('document', sa.Column('extraction_error', sa.String(length=1000), nullable=True))
    op.add_column('document', sa.Column('extraction_stats', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")))
    op.create_index(op.f('ix_document_agreement_id'), 'document', ['agreement_id'], unique=False)
    op.create_foreign_key(op.f('fk_document_agreement_id_agreement'), 'document', 'agreement', ['agreement_id'], ['id'], ondelete='CASCADE')
    op.create_check_constraint('extraction_status_valid', 'document', "extraction_status IN ('queued', 'running', 'succeeded', 'failed')")


def downgrade() -> None:
    op.drop_constraint(op.f('ck_document_extraction_status_valid'), 'document', type_='check')
    op.drop_constraint(op.f('fk_document_agreement_id_agreement'), 'document', type_='foreignkey')
    op.drop_index(op.f('ix_document_agreement_id'), table_name='document')
    op.drop_column('document', 'extraction_stats')
    op.drop_column('document', 'extraction_error')
    op.drop_column('document', 'extraction_status')
    op.drop_column('document', 'agreement_id')
