"""assistant BE-034

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-30
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0006'
down_revision = '0005'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('assistant_conversation',
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('title', sa.String(length=200), nullable=False),
    sa.Column('messages', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('pending_notes', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('org_id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['org_id'], ['organization.id'], name=op.f('fk_assistant_conversation_org_id_organization'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['app_user.id'], name=op.f('fk_assistant_conversation_user_id_app_user'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_assistant_conversation'))
    )
    op.create_index(op.f('ix_assistant_conversation_org_id'), 'assistant_conversation', ['org_id'], unique=False)
    op.create_index(op.f('ix_assistant_conversation_user_id'), 'assistant_conversation', ['user_id'], unique=False)
    op.create_table('assistant_action',
    sa.Column('conversation_id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('tool_use_id', sa.String(length=100), nullable=False),
    sa.Column('tool', sa.String(length=60), nullable=False),
    sa.Column('params', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('summary', sa.Text(), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('result', sa.Text(), nullable=True),
    sa.Column('decided_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('org_id', sa.UUID(), nullable=False),
    sa.CheckConstraint("status IN ('proposed', 'confirmed', 'cancelled', 'failed')", name=op.f('ck_assistant_action_status_valid')),
    sa.ForeignKeyConstraint(['conversation_id'], ['assistant_conversation.id'], name=op.f('fk_assistant_action_conversation_id_assistant_conversation'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['org_id'], ['organization.id'], name=op.f('fk_assistant_action_org_id_organization'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['app_user.id'], name=op.f('fk_assistant_action_user_id_app_user'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_assistant_action'))
    )
    op.create_index(op.f('ix_assistant_action_conversation_id'), 'assistant_action', ['conversation_id'], unique=False)
    op.create_index(op.f('ix_assistant_action_org_id'), 'assistant_action', ['org_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_assistant_action_org_id'), table_name='assistant_action')
    op.drop_index(op.f('ix_assistant_action_conversation_id'), table_name='assistant_action')
    op.drop_table('assistant_action')
    op.drop_index(op.f('ix_assistant_conversation_user_id'), table_name='assistant_conversation')
    op.drop_index(op.f('ix_assistant_conversation_org_id'), table_name='assistant_conversation')
    op.drop_table('assistant_conversation')
