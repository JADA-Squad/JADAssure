"""canonical model BE-001

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-26
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('organization',
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('short_code', sa.String(length=12), nullable=False),
    sa.Column('business_type', sa.String(length=40), nullable=False),
    sa.Column('settings', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('is_demo', sa.Boolean(), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("business_type IN ('professional_services', 'subscription_software', 'distribution', 'other')", name=op.f('ck_organization_business_type_valid')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_organization')),
    sa.UniqueConstraint('short_code', name=op.f('uq_organization_short_code'))
    )
    op.create_table('app_user',
    sa.Column('org_id', sa.UUID(), nullable=False),
    sa.Column('email', sa.String(length=320), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('password_hash', sa.String(length=100), nullable=False),
    sa.Column('role', sa.String(length=20), nullable=False),
    sa.Column('active', sa.Boolean(), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("role IN ('admin', 'analyst', 'approver', 'commercial', 'executive')", name=op.f('ck_app_user_role_valid')),
    sa.ForeignKeyConstraint(['org_id'], ['organization.id'], name=op.f('fk_app_user_org_id_organization'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_app_user')),
    sa.UniqueConstraint('email', name=op.f('uq_app_user_email'))
    )
    op.create_index(op.f('ix_app_user_org_id'), 'app_user', ['org_id'], unique=False)
    op.create_table('audit_event',
    sa.Column('org_id', sa.UUID(), nullable=False),
    sa.Column('seq', sa.BigInteger(), nullable=False),
    sa.Column('actor_id', sa.UUID(), nullable=True),
    sa.Column('action', sa.String(length=80), nullable=False),
    sa.Column('entity', sa.String(length=80), nullable=False),
    sa.Column('entity_id', sa.String(length=80), nullable=True),
    sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('occurred_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('prev_hash', sa.CHAR(length=64), nullable=False),
    sa.Column('hash', sa.CHAR(length=64), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['org_id'], ['organization.id'], name=op.f('fk_audit_event_org_id_organization')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_audit_event')),
    sa.UniqueConstraint('org_id', 'seq', name='uq_audit_event_org_seq')
    )
    op.create_index(op.f('ix_audit_event_org_id'), 'audit_event', ['org_id'], unique=False)
    op.create_table('check_run',
    sa.Column('trigger', sa.String(length=20), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('rule_version_ids', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('stats', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('error', sa.String(length=1000), nullable=True),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('requested_by', sa.UUID(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('org_id', sa.UUID(), nullable=False),
    sa.CheckConstraint("status IN ('queued', 'running', 'succeeded', 'failed')", name=op.f('ck_check_run_status_valid')),
    sa.CheckConstraint("trigger IN ('manual', 'schedule')", name=op.f('ck_check_run_trigger_valid')),
    sa.ForeignKeyConstraint(['org_id'], ['organization.id'], name=op.f('fk_check_run_org_id_organization'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_check_run'))
    )
    op.create_index(op.f('ix_check_run_org_id'), 'check_run', ['org_id'], unique=False)
    op.create_table('data_source',
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('kind', sa.String(length=20), nullable=False),
    sa.Column('connector_key', sa.String(length=80), nullable=True),
    sa.Column('is_demo', sa.Boolean(), nullable=False),
    sa.Column('mapping', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('org_id', sa.UUID(), nullable=False),
    sa.CheckConstraint("kind IN ('csv', 'connector')", name=op.f('ck_data_source_kind_valid')),
    sa.ForeignKeyConstraint(['org_id'], ['organization.id'], name=op.f('fk_data_source_org_id_organization'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_data_source'))
    )
    op.create_index(op.f('ix_data_source_org_id'), 'data_source', ['org_id'], unique=False)
    op.create_table('document',
    sa.Column('filename', sa.String(length=255), nullable=False),
    sa.Column('media_type', sa.String(length=100), nullable=False),
    sa.Column('storage_key', sa.String(length=255), nullable=False),
    sa.Column('sha256', sa.CHAR(length=64), nullable=False),
    sa.Column('size_bytes', sa.BigInteger(), nullable=False),
    sa.Column('uploaded_by', sa.UUID(), nullable=True),
    sa.Column('text_extracted', sa.Text(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('org_id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['org_id'], ['organization.id'], name=op.f('fk_document_org_id_organization'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_document'))
    )
    op.create_index(op.f('ix_document_org_id'), 'document', ['org_id'], unique=False)
    op.create_table('job',
    sa.Column('org_id', sa.UUID(), nullable=True),
    sa.Column('kind', sa.String(length=40), nullable=False),
    sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('attempts', sa.Integer(), nullable=False),
    sa.Column('last_error', sa.String(length=2000), nullable=True),
    sa.Column('run_after', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("status IN ('queued', 'running', 'succeeded', 'failed')", name=op.f('ck_job_status_valid')),
    sa.ForeignKeyConstraint(['org_id'], ['organization.id'], name=op.f('fk_job_org_id_organization'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_job'))
    )
    op.create_index(op.f('ix_job_org_id'), 'job', ['org_id'], unique=False)
    op.create_index(op.f('ix_job_status'), 'job', ['status'], unique=False)
    op.create_table('rule',
    sa.Column('check_type', sa.String(length=40), nullable=False),
    sa.Column('active_version_id', sa.UUID(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('org_id', sa.UUID(), nullable=False),
    sa.CheckConstraint("check_type IN ('delivered_not_billed', 'incorrect_rate', 'expired_discount', 'missed_increase', 'credit_outside_policy')", name=op.f('ck_rule_check_type_valid')),
    sa.ForeignKeyConstraint(['org_id'], ['organization.id'], name=op.f('fk_rule_org_id_organization'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_rule')),
    sa.UniqueConstraint('org_id', 'check_type', name='uq_rule_org_check')
    )
    op.create_index(op.f('ix_rule_org_id'), 'rule', ['org_id'], unique=False)
    op.create_table('import_batch',
    sa.Column('data_source_id', sa.UUID(), nullable=False),
    sa.Column('record_type', sa.String(length=40), nullable=False),
    sa.Column('filename', sa.String(length=255), nullable=False),
    sa.Column('file_ref', sa.String(length=255), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('counts', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('profile', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('error_report_ref', sa.String(length=255), nullable=True),
    sa.Column('error', sa.String(length=1000), nullable=True),
    sa.Column('created_by', sa.UUID(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('org_id', sa.UUID(), nullable=False),
    sa.CheckConstraint("record_type IN ('customer', 'agreement', 'agreement_version', 'commercial_term', 'billable_event', 'invoice', 'invoice_line', 'credit', 'payment', 'payment_allocation', 'cost_record')", name=op.f('ck_import_batch_record_type_valid')),
    sa.CheckConstraint("status IN ('profiled', 'queued', 'running', 'succeeded', 'failed')", name=op.f('ck_import_batch_status_valid')),
    sa.ForeignKeyConstraint(['data_source_id'], ['data_source.id'], name=op.f('fk_import_batch_data_source_id_data_source'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['org_id'], ['organization.id'], name=op.f('fk_import_batch_org_id_organization'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_import_batch'))
    )
    op.create_index(op.f('ix_import_batch_data_source_id'), 'import_batch', ['data_source_id'], unique=False)
    op.create_index(op.f('ix_import_batch_org_id'), 'import_batch', ['org_id'], unique=False)
    op.create_table('rule_version',
    sa.Column('rule_id', sa.UUID(), nullable=False),
    sa.Column('version_no', sa.Integer(), nullable=False),
    sa.Column('params', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('created_by', sa.UUID(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('org_id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['org_id'], ['organization.id'], name=op.f('fk_rule_version_org_id_organization'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['rule_id'], ['rule.id'], name=op.f('fk_rule_version_rule_id_rule'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_rule_version')),
    sa.UniqueConstraint('rule_id', 'version_no', name='uq_rule_version_no')
    )
    op.create_index(op.f('ix_rule_version_org_id'), 'rule_version', ['org_id'], unique=False)
    op.create_index(op.f('ix_rule_version_rule_id'), 'rule_version', ['rule_id'], unique=False)
    # rule <-> rule_version is circular; add this FK once both tables exist.
    op.create_foreign_key(op.f('fk_rule_active_version_id_rule_version'), 'rule', 'rule_version', ['active_version_id'], ['id'], ondelete='SET NULL')
    op.create_table('cost_record',
    sa.Column('item_code', sa.String(length=80), nullable=False),
    sa.Column('unit_cost', sa.Numeric(precision=19, scale=6), nullable=False),
    sa.Column('currency', sa.CHAR(length=3), nullable=False),
    sa.Column('effective_from', sa.Date(), nullable=False),
    sa.Column('effective_to', sa.Date(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('org_id', sa.UUID(), nullable=False),
    sa.Column('source_record_id', sa.String(length=200), nullable=True),
    sa.Column('source_payload', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('source_hash', sa.CHAR(length=64), nullable=True),
    sa.Column('data_source_id', sa.UUID(), nullable=True),
    sa.Column('import_id', sa.UUID(), nullable=True),
    sa.ForeignKeyConstraint(['data_source_id'], ['data_source.id'], name=op.f('fk_cost_record_data_source_id_data_source'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['import_id'], ['import_batch.id'], name=op.f('fk_cost_record_import_id_import_batch'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['org_id'], ['organization.id'], name=op.f('fk_cost_record_org_id_organization'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_cost_record')),
    sa.UniqueConstraint('org_id', 'data_source_id', 'source_record_id', name='uq_cost_record_source_key')
    )
    op.create_index(op.f('ix_cost_record_item_code'), 'cost_record', ['item_code'], unique=False)
    op.create_index(op.f('ix_cost_record_org_id'), 'cost_record', ['org_id'], unique=False)
    op.create_table('customer',
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('currency', sa.CHAR(length=3), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('org_id', sa.UUID(), nullable=False),
    sa.Column('source_record_id', sa.String(length=200), nullable=True),
    sa.Column('source_payload', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('source_hash', sa.CHAR(length=64), nullable=True),
    sa.Column('data_source_id', sa.UUID(), nullable=True),
    sa.Column('import_id', sa.UUID(), nullable=True),
    sa.ForeignKeyConstraint(['data_source_id'], ['data_source.id'], name=op.f('fk_customer_data_source_id_data_source'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['import_id'], ['import_batch.id'], name=op.f('fk_customer_import_id_import_batch'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['org_id'], ['organization.id'], name=op.f('fk_customer_org_id_organization'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_customer')),
    sa.UniqueConstraint('org_id', 'data_source_id', 'source_record_id', name='uq_customer_source_key')
    )
    op.create_index(op.f('ix_customer_org_id'), 'customer', ['org_id'], unique=False)
    op.create_table('agreement',
    sa.Column('customer_id', sa.UUID(), nullable=False),
    sa.Column('title', sa.String(length=200), nullable=False),
    sa.Column('start_date', sa.Date(), nullable=False),
    sa.Column('end_date', sa.Date(), nullable=True),
    sa.Column('billing_frequency', sa.String(length=20), nullable=False),
    sa.Column('currency', sa.CHAR(length=3), nullable=False),
    sa.Column('document_id', sa.UUID(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('org_id', sa.UUID(), nullable=False),
    sa.Column('source_record_id', sa.String(length=200), nullable=True),
    sa.Column('source_payload', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('source_hash', sa.CHAR(length=64), nullable=True),
    sa.Column('data_source_id', sa.UUID(), nullable=True),
    sa.Column('import_id', sa.UUID(), nullable=True),
    sa.CheckConstraint("billing_frequency IN ('monthly', 'quarterly', 'annual', 'per_event', 'milestone')", name=op.f('ck_agreement_billing_frequency_valid')),
    sa.ForeignKeyConstraint(['customer_id'], ['customer.id'], name=op.f('fk_agreement_customer_id_customer'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['data_source_id'], ['data_source.id'], name=op.f('fk_agreement_data_source_id_data_source'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['document_id'], ['document.id'], name=op.f('fk_agreement_document_id_document'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['import_id'], ['import_batch.id'], name=op.f('fk_agreement_import_id_import_batch'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['org_id'], ['organization.id'], name=op.f('fk_agreement_org_id_organization'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_agreement')),
    sa.UniqueConstraint('org_id', 'data_source_id', 'source_record_id', name='uq_agreement_source_key')
    )
    op.create_index(op.f('ix_agreement_customer_id'), 'agreement', ['customer_id'], unique=False)
    op.create_index(op.f('ix_agreement_org_id'), 'agreement', ['org_id'], unique=False)
    op.create_table('invoice',
    sa.Column('customer_id', sa.UUID(), nullable=False),
    sa.Column('number', sa.String(length=80), nullable=False),
    sa.Column('invoice_date', sa.Date(), nullable=False),
    sa.Column('currency', sa.CHAR(length=3), nullable=False),
    sa.Column('status', sa.String(length=40), nullable=True),
    sa.Column('correction_reference', sa.String(length=40), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('org_id', sa.UUID(), nullable=False),
    sa.Column('source_record_id', sa.String(length=200), nullable=True),
    sa.Column('source_payload', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('source_hash', sa.CHAR(length=64), nullable=True),
    sa.Column('data_source_id', sa.UUID(), nullable=True),
    sa.Column('import_id', sa.UUID(), nullable=True),
    sa.ForeignKeyConstraint(['customer_id'], ['customer.id'], name=op.f('fk_invoice_customer_id_customer'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['data_source_id'], ['data_source.id'], name=op.f('fk_invoice_data_source_id_data_source'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['import_id'], ['import_batch.id'], name=op.f('fk_invoice_import_id_import_batch'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['org_id'], ['organization.id'], name=op.f('fk_invoice_org_id_organization'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_invoice')),
    sa.UniqueConstraint('org_id', 'data_source_id', 'source_record_id', name='uq_invoice_source_key')
    )
    op.create_index(op.f('ix_invoice_correction_reference'), 'invoice', ['correction_reference'], unique=False)
    op.create_index(op.f('ix_invoice_customer_id'), 'invoice', ['customer_id'], unique=False)
    op.create_index(op.f('ix_invoice_org_id'), 'invoice', ['org_id'], unique=False)
    op.create_table('payment',
    sa.Column('customer_id', sa.UUID(), nullable=False),
    sa.Column('amount', sa.Numeric(precision=19, scale=4), nullable=False),
    sa.Column('currency', sa.CHAR(length=3), nullable=False),
    sa.Column('payment_date', sa.Date(), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('org_id', sa.UUID(), nullable=False),
    sa.Column('source_record_id', sa.String(length=200), nullable=True),
    sa.Column('source_payload', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('source_hash', sa.CHAR(length=64), nullable=True),
    sa.Column('data_source_id', sa.UUID(), nullable=True),
    sa.Column('import_id', sa.UUID(), nullable=True),
    sa.ForeignKeyConstraint(['customer_id'], ['customer.id'], name=op.f('fk_payment_customer_id_customer'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['data_source_id'], ['data_source.id'], name=op.f('fk_payment_data_source_id_data_source'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['import_id'], ['import_batch.id'], name=op.f('fk_payment_import_id_import_batch'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['org_id'], ['organization.id'], name=op.f('fk_payment_org_id_organization'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_payment')),
    sa.UniqueConstraint('org_id', 'data_source_id', 'source_record_id', name='uq_payment_source_key')
    )
    op.create_index(op.f('ix_payment_customer_id'), 'payment', ['customer_id'], unique=False)
    op.create_index(op.f('ix_payment_org_id'), 'payment', ['org_id'], unique=False)
    op.create_table('agreement_version',
    sa.Column('agreement_id', sa.UUID(), nullable=False),
    sa.Column('version_no', sa.Integer(), nullable=False),
    sa.Column('effective_from', sa.Date(), nullable=False),
    sa.Column('effective_to', sa.Date(), nullable=True),
    sa.Column('reason', sa.String(length=500), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('org_id', sa.UUID(), nullable=False),
    sa.Column('source_record_id', sa.String(length=200), nullable=True),
    sa.Column('source_payload', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('source_hash', sa.CHAR(length=64), nullable=True),
    sa.Column('data_source_id', sa.UUID(), nullable=True),
    sa.Column('import_id', sa.UUID(), nullable=True),
    sa.ForeignKeyConstraint(['agreement_id'], ['agreement.id'], name=op.f('fk_agreement_version_agreement_id_agreement'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['data_source_id'], ['data_source.id'], name=op.f('fk_agreement_version_data_source_id_data_source'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['import_id'], ['import_batch.id'], name=op.f('fk_agreement_version_import_id_import_batch'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['org_id'], ['organization.id'], name=op.f('fk_agreement_version_org_id_organization'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_agreement_version')),
    sa.UniqueConstraint('org_id', 'data_source_id', 'source_record_id', name='uq_agreement_version_source_key')
    )
    op.create_index(op.f('ix_agreement_version_agreement_id'), 'agreement_version', ['agreement_id'], unique=False)
    op.create_index(op.f('ix_agreement_version_org_id'), 'agreement_version', ['org_id'], unique=False)
    op.create_table('billable_event',
    sa.Column('customer_id', sa.UUID(), nullable=False),
    sa.Column('agreement_id', sa.UUID(), nullable=True),
    sa.Column('item_code', sa.String(length=80), nullable=False),
    sa.Column('quantity', sa.Numeric(precision=19, scale=6), nullable=False),
    sa.Column('unit', sa.String(length=40), nullable=True),
    sa.Column('service_date', sa.Date(), nullable=False),
    sa.Column('billing_date', sa.Date(), nullable=True),
    sa.Column('currency', sa.CHAR(length=3), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('org_id', sa.UUID(), nullable=False),
    sa.Column('source_record_id', sa.String(length=200), nullable=True),
    sa.Column('source_payload', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('source_hash', sa.CHAR(length=64), nullable=True),
    sa.Column('data_source_id', sa.UUID(), nullable=True),
    sa.Column('import_id', sa.UUID(), nullable=True),
    sa.ForeignKeyConstraint(['agreement_id'], ['agreement.id'], name=op.f('fk_billable_event_agreement_id_agreement'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['customer_id'], ['customer.id'], name=op.f('fk_billable_event_customer_id_customer'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['data_source_id'], ['data_source.id'], name=op.f('fk_billable_event_data_source_id_data_source'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['import_id'], ['import_batch.id'], name=op.f('fk_billable_event_import_id_import_batch'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['org_id'], ['organization.id'], name=op.f('fk_billable_event_org_id_organization'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_billable_event')),
    sa.UniqueConstraint('org_id', 'data_source_id', 'source_record_id', name='uq_billable_event_source_key')
    )
    op.create_index(op.f('ix_billable_event_agreement_id'), 'billable_event', ['agreement_id'], unique=False)
    op.create_index(op.f('ix_billable_event_customer_id'), 'billable_event', ['customer_id'], unique=False)
    op.create_index(op.f('ix_billable_event_org_id'), 'billable_event', ['org_id'], unique=False)
    op.create_table('credit',
    sa.Column('customer_id', sa.UUID(), nullable=False),
    sa.Column('invoice_id', sa.UUID(), nullable=True),
    sa.Column('amount', sa.Numeric(precision=19, scale=4), nullable=False),
    sa.Column('currency', sa.CHAR(length=3), nullable=False),
    sa.Column('reason_code', sa.String(length=80), nullable=True),
    sa.Column('approval_ref', sa.String(length=80), nullable=True),
    sa.Column('credit_date', sa.Date(), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('org_id', sa.UUID(), nullable=False),
    sa.Column('source_record_id', sa.String(length=200), nullable=True),
    sa.Column('source_payload', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('source_hash', sa.CHAR(length=64), nullable=True),
    sa.Column('data_source_id', sa.UUID(), nullable=True),
    sa.Column('import_id', sa.UUID(), nullable=True),
    sa.ForeignKeyConstraint(['customer_id'], ['customer.id'], name=op.f('fk_credit_customer_id_customer'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['data_source_id'], ['data_source.id'], name=op.f('fk_credit_data_source_id_data_source'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['import_id'], ['import_batch.id'], name=op.f('fk_credit_import_id_import_batch'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['invoice_id'], ['invoice.id'], name=op.f('fk_credit_invoice_id_invoice'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['org_id'], ['organization.id'], name=op.f('fk_credit_org_id_organization'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_credit')),
    sa.UniqueConstraint('org_id', 'data_source_id', 'source_record_id', name='uq_credit_source_key')
    )
    op.create_index(op.f('ix_credit_customer_id'), 'credit', ['customer_id'], unique=False)
    op.create_index(op.f('ix_credit_org_id'), 'credit', ['org_id'], unique=False)
    op.create_table('finding',
    sa.Column('fingerprint', sa.CHAR(length=64), nullable=False),
    sa.Column('family', sa.String(length=20), nullable=False),
    sa.Column('check_type', sa.String(length=40), nullable=False),
    sa.Column('also_detected_by', postgresql.ARRAY(sa.String(length=40)), nullable=False),
    sa.Column('customer_id', sa.UUID(), nullable=True),
    sa.Column('agreement_id', sa.UUID(), nullable=True),
    sa.Column('item_code', sa.String(length=80), nullable=True),
    sa.Column('period_start', sa.Date(), nullable=True),
    sa.Column('period_end', sa.Date(), nullable=True),
    sa.Column('value', sa.Numeric(precision=19, scale=4), nullable=False),
    sa.Column('currency', sa.CHAR(length=3), nullable=False),
    sa.Column('confidence', sa.String(length=10), nullable=False),
    sa.Column('reason', sa.Text(), nullable=False),
    sa.Column('calculation', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('evidence', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('rule_version_id', sa.UUID(), nullable=False),
    sa.Column('recommended_action', sa.String(length=500), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('owner_id', sa.UUID(), nullable=True),
    sa.Column('proposer_id', sa.UUID(), nullable=True),
    sa.Column('root_cause', sa.String(length=500), nullable=True),
    sa.Column('recurrence_of_id', sa.UUID(), nullable=True),
    sa.Column('first_run_id', sa.UUID(), nullable=False),
    sa.Column('last_run_id', sa.UUID(), nullable=False),
    sa.Column('ai_summary', sa.Text(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('org_id', sa.UUID(), nullable=False),
    sa.CheckConstraint("check_type IN ('delivered_not_billed', 'incorrect_rate', 'expired_discount', 'missed_increase', 'credit_outside_policy')", name=op.f('ck_finding_check_type_valid')),
    sa.CheckConstraint("confidence IN ('high', 'medium', 'low')", name=op.f('ck_finding_confidence_valid')),
    sa.CheckConstraint("family IN ('unbilled', 'price', 'credit')", name=op.f('ck_finding_family_valid')),
    sa.CheckConstraint("status IN ('open', 'in_review', 'proposed', 'approved', 'billed', 'recovered', 'rejected', 'closed_no_recovery')", name=op.f('ck_finding_status_valid')),
    sa.ForeignKeyConstraint(['agreement_id'], ['agreement.id'], name=op.f('fk_finding_agreement_id_agreement'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['customer_id'], ['customer.id'], name=op.f('fk_finding_customer_id_customer'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['first_run_id'], ['check_run.id'], name=op.f('fk_finding_first_run_id_check_run')),
    sa.ForeignKeyConstraint(['last_run_id'], ['check_run.id'], name=op.f('fk_finding_last_run_id_check_run')),
    sa.ForeignKeyConstraint(['org_id'], ['organization.id'], name=op.f('fk_finding_org_id_organization'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['owner_id'], ['app_user.id'], name=op.f('fk_finding_owner_id_app_user')),
    sa.ForeignKeyConstraint(['proposer_id'], ['app_user.id'], name=op.f('fk_finding_proposer_id_app_user')),
    sa.ForeignKeyConstraint(['recurrence_of_id'], ['finding.id'], name=op.f('fk_finding_recurrence_of_id_finding'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['rule_version_id'], ['rule_version.id'], name=op.f('fk_finding_rule_version_id_rule_version')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_finding')),
    sa.UniqueConstraint('org_id', 'fingerprint', name='uq_finding_org_fingerprint')
    )
    op.create_index(op.f('ix_finding_customer_id'), 'finding', ['customer_id'], unique=False)
    op.create_index(op.f('ix_finding_org_id'), 'finding', ['org_id'], unique=False)
    op.create_index(op.f('ix_finding_status'), 'finding', ['status'], unique=False)
    op.create_table('invoice_line',
    sa.Column('invoice_id', sa.UUID(), nullable=False),
    sa.Column('agreement_id', sa.UUID(), nullable=True),
    sa.Column('item_code', sa.String(length=80), nullable=False),
    sa.Column('quantity', sa.Numeric(precision=19, scale=6), nullable=False),
    sa.Column('unit_price', sa.Numeric(precision=19, scale=6), nullable=False),
    sa.Column('discount_pct', sa.Numeric(precision=19, scale=6), nullable=False),
    sa.Column('net_amount', sa.Numeric(precision=19, scale=4), nullable=False),
    sa.Column('tax_amount', sa.Numeric(precision=19, scale=4), nullable=False),
    sa.Column('service_period_start', sa.Date(), nullable=True),
    sa.Column('service_period_end', sa.Date(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('org_id', sa.UUID(), nullable=False),
    sa.Column('source_record_id', sa.String(length=200), nullable=True),
    sa.Column('source_payload', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('source_hash', sa.CHAR(length=64), nullable=True),
    sa.Column('data_source_id', sa.UUID(), nullable=True),
    sa.Column('import_id', sa.UUID(), nullable=True),
    sa.ForeignKeyConstraint(['agreement_id'], ['agreement.id'], name=op.f('fk_invoice_line_agreement_id_agreement'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['data_source_id'], ['data_source.id'], name=op.f('fk_invoice_line_data_source_id_data_source'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['import_id'], ['import_batch.id'], name=op.f('fk_invoice_line_import_id_import_batch'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['invoice_id'], ['invoice.id'], name=op.f('fk_invoice_line_invoice_id_invoice'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['org_id'], ['organization.id'], name=op.f('fk_invoice_line_org_id_organization'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_invoice_line')),
    sa.UniqueConstraint('org_id', 'data_source_id', 'source_record_id', name='uq_invoice_line_source_key')
    )
    op.create_index(op.f('ix_invoice_line_agreement_id'), 'invoice_line', ['agreement_id'], unique=False)
    op.create_index(op.f('ix_invoice_line_invoice_id'), 'invoice_line', ['invoice_id'], unique=False)
    op.create_index(op.f('ix_invoice_line_org_id'), 'invoice_line', ['org_id'], unique=False)
    op.create_table('payment_allocation',
    sa.Column('payment_id', sa.UUID(), nullable=False),
    sa.Column('invoice_id', sa.UUID(), nullable=False),
    sa.Column('amount', sa.Numeric(precision=19, scale=4), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('org_id', sa.UUID(), nullable=False),
    sa.Column('source_record_id', sa.String(length=200), nullable=True),
    sa.Column('source_payload', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('source_hash', sa.CHAR(length=64), nullable=True),
    sa.Column('data_source_id', sa.UUID(), nullable=True),
    sa.Column('import_id', sa.UUID(), nullable=True),
    sa.ForeignKeyConstraint(['data_source_id'], ['data_source.id'], name=op.f('fk_payment_allocation_data_source_id_data_source'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['import_id'], ['import_batch.id'], name=op.f('fk_payment_allocation_import_id_import_batch'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['invoice_id'], ['invoice.id'], name=op.f('fk_payment_allocation_invoice_id_invoice'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['org_id'], ['organization.id'], name=op.f('fk_payment_allocation_org_id_organization'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['payment_id'], ['payment.id'], name=op.f('fk_payment_allocation_payment_id_payment'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_payment_allocation')),
    sa.UniqueConstraint('org_id', 'data_source_id', 'source_record_id', name='uq_payment_allocation_source_key')
    )
    op.create_index(op.f('ix_payment_allocation_invoice_id'), 'payment_allocation', ['invoice_id'], unique=False)
    op.create_index(op.f('ix_payment_allocation_org_id'), 'payment_allocation', ['org_id'], unique=False)
    op.create_index(op.f('ix_payment_allocation_payment_id'), 'payment_allocation', ['payment_id'], unique=False)
    op.create_table('approval',
    sa.Column('finding_id', sa.UUID(), nullable=False),
    sa.Column('approver_id', sa.UUID(), nullable=False),
    sa.Column('decision', sa.String(length=20), nullable=False),
    sa.Column('note', sa.Text(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('org_id', sa.UUID(), nullable=False),
    sa.CheckConstraint("decision IN ('approved', 'sent_back', 'written_off')", name=op.f('ck_approval_decision_valid')),
    sa.ForeignKeyConstraint(['approver_id'], ['app_user.id'], name=op.f('fk_approval_approver_id_app_user')),
    sa.ForeignKeyConstraint(['finding_id'], ['finding.id'], name=op.f('fk_approval_finding_id_finding'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['org_id'], ['organization.id'], name=op.f('fk_approval_org_id_organization'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_approval'))
    )
    op.create_index(op.f('ix_approval_finding_id'), 'approval', ['finding_id'], unique=False)
    op.create_index(op.f('ix_approval_org_id'), 'approval', ['org_id'], unique=False)
    op.create_table('commercial_term',
    sa.Column('agreement_version_id', sa.UUID(), nullable=False),
    sa.Column('item_code', sa.String(length=80), nullable=True),
    sa.Column('term_type', sa.String(length=20), nullable=False),
    sa.Column('value', sa.Numeric(precision=19, scale=6), nullable=False),
    sa.Column('unit', sa.String(length=40), nullable=True),
    sa.Column('currency', sa.CHAR(length=3), nullable=True),
    sa.Column('effective_from', sa.Date(), nullable=False),
    sa.Column('effective_to', sa.Date(), nullable=True),
    sa.Column('approval_ref', sa.String(length=80), nullable=True),
    sa.Column('params', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('ambiguous', sa.Boolean(), nullable=False),
    sa.Column('ambiguity_reason', sa.String(length=500), nullable=True),
    sa.Column('source_passage', sa.Text(), nullable=True),
    sa.Column('document_id', sa.UUID(), nullable=True),
    sa.Column('origin', sa.String(length=20), nullable=False),
    sa.Column('confirmed_by', sa.UUID(), nullable=True),
    sa.Column('confirmed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('org_id', sa.UUID(), nullable=False),
    sa.Column('source_record_id', sa.String(length=200), nullable=True),
    sa.Column('source_payload', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('source_hash', sa.CHAR(length=64), nullable=True),
    sa.Column('data_source_id', sa.UUID(), nullable=True),
    sa.Column('import_id', sa.UUID(), nullable=True),
    sa.CheckConstraint("origin IN ('import', 'extraction', 'manual')", name=op.f('ck_commercial_term_origin_valid')),
    sa.CheckConstraint("status IN ('proposed', 'confirmed', 'rejected')", name=op.f('ck_commercial_term_status_valid')),
    sa.CheckConstraint("term_type IN ('rate', 'discount', 'escalation', 'credit_policy', 'minimum')", name=op.f('ck_commercial_term_term_type_valid')),
    sa.ForeignKeyConstraint(['agreement_version_id'], ['agreement_version.id'], name=op.f('fk_commercial_term_agreement_version_id_agreement_version'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['data_source_id'], ['data_source.id'], name=op.f('fk_commercial_term_data_source_id_data_source'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['document_id'], ['document.id'], name=op.f('fk_commercial_term_document_id_document'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['import_id'], ['import_batch.id'], name=op.f('fk_commercial_term_import_id_import_batch'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['org_id'], ['organization.id'], name=op.f('fk_commercial_term_org_id_organization'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_commercial_term')),
    sa.UniqueConstraint('org_id', 'data_source_id', 'source_record_id', name='uq_commercial_term_source_key')
    )
    op.create_index(op.f('ix_commercial_term_agreement_version_id'), 'commercial_term', ['agreement_version_id'], unique=False)
    op.create_index(op.f('ix_commercial_term_org_id'), 'commercial_term', ['org_id'], unique=False)
    op.create_index(op.f('ix_commercial_term_status'), 'commercial_term', ['status'], unique=False)
    op.create_table('correction',
    sa.Column('finding_id', sa.UUID(), nullable=False),
    sa.Column('reference', sa.String(length=40), nullable=False),
    sa.Column('kind', sa.String(length=30), nullable=False),
    sa.Column('lines', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('amount', sa.Numeric(precision=19, scale=4), nullable=False),
    sa.Column('currency', sa.CHAR(length=3), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('matched_invoice_ids', postgresql.ARRAY(sa.UUID()), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('org_id', sa.UUID(), nullable=False),
    sa.CheckConstraint("kind IN ('supplementary_invoice', 'credit_reversal')", name=op.f('ck_correction_kind_valid')),
    sa.CheckConstraint("status IN ('prepared', 'billed', 'partially_paid', 'paid')", name=op.f('ck_correction_status_valid')),
    sa.ForeignKeyConstraint(['finding_id'], ['finding.id'], name=op.f('fk_correction_finding_id_finding'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['org_id'], ['organization.id'], name=op.f('fk_correction_org_id_organization'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_correction')),
    sa.UniqueConstraint('finding_id', name=op.f('uq_correction_finding_id')),
    sa.UniqueConstraint('reference', name=op.f('uq_correction_reference'))
    )
    op.create_index(op.f('ix_correction_org_id'), 'correction', ['org_id'], unique=False)
    op.create_table('investigation_event',
    sa.Column('finding_id', sa.UUID(), nullable=False),
    sa.Column('actor_id', sa.UUID(), nullable=True),
    sa.Column('kind', sa.String(length=20), nullable=False),
    sa.Column('body', sa.Text(), nullable=True),
    sa.Column('data', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('org_id', sa.UUID(), nullable=False),
    sa.CheckConstraint("kind IN ('comment', 'assign', 'status')", name=op.f('ck_investigation_event_kind_valid')),
    sa.ForeignKeyConstraint(['actor_id'], ['app_user.id'], name=op.f('fk_investigation_event_actor_id_app_user')),
    sa.ForeignKeyConstraint(['finding_id'], ['finding.id'], name=op.f('fk_investigation_event_finding_id_finding'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['org_id'], ['organization.id'], name=op.f('fk_investigation_event_org_id_organization'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_investigation_event'))
    )
    op.create_index(op.f('ix_investigation_event_finding_id'), 'investigation_event', ['finding_id'], unique=False)
    op.create_index(op.f('ix_investigation_event_org_id'), 'investigation_event', ['org_id'], unique=False)
    op.create_table('recovery_event',
    sa.Column('correction_id', sa.UUID(), nullable=False),
    sa.Column('kind', sa.String(length=10), nullable=False),
    sa.Column('amount', sa.Numeric(precision=19, scale=4), nullable=False),
    sa.Column('source_entity', sa.String(length=40), nullable=False),
    sa.Column('source_entity_id', sa.UUID(), nullable=False),
    sa.Column('occurred_on', sa.Date(), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('org_id', sa.UUID(), nullable=False),
    sa.CheckConstraint("kind IN ('billed', 'cash')", name=op.f('ck_recovery_event_kind_valid')),
    sa.ForeignKeyConstraint(['correction_id'], ['correction.id'], name=op.f('fk_recovery_event_correction_id_correction'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['org_id'], ['organization.id'], name=op.f('fk_recovery_event_org_id_organization'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_recovery_event')),
    sa.UniqueConstraint('correction_id', 'kind', 'source_entity_id', name='uq_recovery_event_source')
    )
    op.create_index(op.f('ix_recovery_event_correction_id'), 'recovery_event', ['correction_id'], unique=False)
    op.create_index(op.f('ix_recovery_event_org_id'), 'recovery_event', ['org_id'], unique=False)


def downgrade() -> None:
    op.drop_constraint(op.f('fk_rule_active_version_id_rule_version'), 'rule', type_='foreignkey')
    op.drop_index(op.f('ix_recovery_event_org_id'), table_name='recovery_event')
    op.drop_index(op.f('ix_recovery_event_correction_id'), table_name='recovery_event')
    op.drop_table('recovery_event')
    op.drop_index(op.f('ix_investigation_event_org_id'), table_name='investigation_event')
    op.drop_index(op.f('ix_investigation_event_finding_id'), table_name='investigation_event')
    op.drop_table('investigation_event')
    op.drop_index(op.f('ix_correction_org_id'), table_name='correction')
    op.drop_table('correction')
    op.drop_index(op.f('ix_commercial_term_status'), table_name='commercial_term')
    op.drop_index(op.f('ix_commercial_term_org_id'), table_name='commercial_term')
    op.drop_index(op.f('ix_commercial_term_agreement_version_id'), table_name='commercial_term')
    op.drop_table('commercial_term')
    op.drop_index(op.f('ix_approval_org_id'), table_name='approval')
    op.drop_index(op.f('ix_approval_finding_id'), table_name='approval')
    op.drop_table('approval')
    op.drop_index(op.f('ix_payment_allocation_payment_id'), table_name='payment_allocation')
    op.drop_index(op.f('ix_payment_allocation_org_id'), table_name='payment_allocation')
    op.drop_index(op.f('ix_payment_allocation_invoice_id'), table_name='payment_allocation')
    op.drop_table('payment_allocation')
    op.drop_index(op.f('ix_invoice_line_org_id'), table_name='invoice_line')
    op.drop_index(op.f('ix_invoice_line_invoice_id'), table_name='invoice_line')
    op.drop_index(op.f('ix_invoice_line_agreement_id'), table_name='invoice_line')
    op.drop_table('invoice_line')
    op.drop_index(op.f('ix_finding_status'), table_name='finding')
    op.drop_index(op.f('ix_finding_org_id'), table_name='finding')
    op.drop_index(op.f('ix_finding_customer_id'), table_name='finding')
    op.drop_table('finding')
    op.drop_index(op.f('ix_credit_org_id'), table_name='credit')
    op.drop_index(op.f('ix_credit_customer_id'), table_name='credit')
    op.drop_table('credit')
    op.drop_index(op.f('ix_billable_event_org_id'), table_name='billable_event')
    op.drop_index(op.f('ix_billable_event_customer_id'), table_name='billable_event')
    op.drop_index(op.f('ix_billable_event_agreement_id'), table_name='billable_event')
    op.drop_table('billable_event')
    op.drop_index(op.f('ix_agreement_version_org_id'), table_name='agreement_version')
    op.drop_index(op.f('ix_agreement_version_agreement_id'), table_name='agreement_version')
    op.drop_table('agreement_version')
    op.drop_index(op.f('ix_payment_org_id'), table_name='payment')
    op.drop_index(op.f('ix_payment_customer_id'), table_name='payment')
    op.drop_table('payment')
    op.drop_index(op.f('ix_invoice_org_id'), table_name='invoice')
    op.drop_index(op.f('ix_invoice_customer_id'), table_name='invoice')
    op.drop_index(op.f('ix_invoice_correction_reference'), table_name='invoice')
    op.drop_table('invoice')
    op.drop_index(op.f('ix_agreement_org_id'), table_name='agreement')
    op.drop_index(op.f('ix_agreement_customer_id'), table_name='agreement')
    op.drop_table('agreement')
    op.drop_index(op.f('ix_customer_org_id'), table_name='customer')
    op.drop_table('customer')
    op.drop_index(op.f('ix_cost_record_org_id'), table_name='cost_record')
    op.drop_index(op.f('ix_cost_record_item_code'), table_name='cost_record')
    op.drop_table('cost_record')
    op.drop_index(op.f('ix_rule_version_rule_id'), table_name='rule_version')
    op.drop_index(op.f('ix_rule_version_org_id'), table_name='rule_version')
    op.drop_table('rule_version')
    op.drop_index(op.f('ix_import_batch_org_id'), table_name='import_batch')
    op.drop_index(op.f('ix_import_batch_data_source_id'), table_name='import_batch')
    op.drop_table('import_batch')
    op.drop_index(op.f('ix_rule_org_id'), table_name='rule')
    op.drop_table('rule')
    op.drop_index(op.f('ix_job_status'), table_name='job')
    op.drop_index(op.f('ix_job_org_id'), table_name='job')
    op.drop_table('job')
    op.drop_index(op.f('ix_document_org_id'), table_name='document')
    op.drop_table('document')
    op.drop_index(op.f('ix_data_source_org_id'), table_name='data_source')
    op.drop_table('data_source')
    op.drop_index(op.f('ix_check_run_org_id'), table_name='check_run')
    op.drop_table('check_run')
    op.drop_index(op.f('ix_audit_event_org_id'), table_name='audit_event')
    op.drop_table('audit_event')
    op.drop_index(op.f('ix_app_user_org_id'), table_name='app_user')
    op.drop_table('app_user')
    op.drop_table('organization')
