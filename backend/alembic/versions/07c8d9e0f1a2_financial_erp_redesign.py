"""Additive MFEC financial ERP redesign.

Revision ID: 07c8d9e0f1a2
Revises: f6a7b8c9d0e1
"""
from alembic import op
import sqlalchemy as sa

revision = "07c8d9e0f1a2"
down_revision = "f6a7b8c9d0e1"
branch_labels = None
depends_on = None


def _audit_columns():
    return [
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column("deleted_by", sa.String(200)),
    ]


def upgrade():
    for name, column in (
        ("financial_companies", sa.Column("owner_name", sa.String(200))),
        ("financial_companies", sa.Column("address", sa.Text())),
        ("financial_companies", sa.Column("mobile", sa.String(50))),
        ("financial_companies", sa.Column("cooperation_status", sa.String(20), nullable=False, server_default="active")),
        ("financial_companies", sa.Column("cooperation_started_at", sa.Date())),
        ("financial_companies", sa.Column("deleted_at", sa.DateTime(timezone=True))),
        ("financial_companies", sa.Column("deleted_by", sa.String(200))),
        ("financial_member_company_accounts", sa.Column("customer_portal_url", sa.Text())),
        ("financial_member_company_accounts", sa.Column("started_at", sa.Date())),
        ("financial_member_company_accounts", sa.Column("ended_at", sa.Date())),
        ("financial_member_company_accounts", sa.Column("status", sa.String(20), nullable=False, server_default="active")),
        ("financial_member_company_accounts", sa.Column("default_unit_price_override", sa.Numeric(18, 3))),
        ("financial_member_company_accounts", sa.Column("default_mfec_share_type_override", sa.String(20))),
        ("financial_member_company_accounts", sa.Column("default_mfec_share_value_override", sa.Numeric(18, 3))),
        ("financial_member_company_accounts", sa.Column("deleted_at", sa.DateTime(timezone=True))),
        ("financial_member_company_accounts", sa.Column("deleted_by", sa.String(200))),
        ("financial_expenses", sa.Column("deleted_at", sa.DateTime(timezone=True))),
        ("financial_expenses", sa.Column("deleted_by", sa.String(200))),
        ("financial_expenses", sa.Column("restored_at", sa.DateTime(timezone=True))),
        ("financial_expenses", sa.Column("restored_by", sa.String(200))),
    ):
        op.add_column(name, column)

    op.create_table(
        "financial_company_attachments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("financial_companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("contract_id", sa.Integer(), sa.ForeignKey("financial_company_contracts.id", ondelete="SET NULL")),
        sa.Column("document_type", sa.String(40), nullable=False, server_default="contract"),
        sa.Column("object_key", sa.String(500), nullable=False),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("mime_type", sa.String(120), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("uploaded_by", sa.String(200), nullable=False),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("replaced_attachment_id", sa.Integer(), sa.ForeignKey("financial_company_attachments.id", ondelete="SET NULL")),
        *_audit_columns(),
    )
    op.create_index("ix_fin_company_attachment_company", "financial_company_attachments", ["company_id", "deleted_at"])

    op.create_table(
        "financial_pricing_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("financial_companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("unit", sa.String(80), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("notes", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        *_audit_columns(),
        sa.UniqueConstraint("company_id", "name", name="uq_fin_pricing_item_company_name"),
    )
    op.create_index("ix_fin_pricing_item_company_active", "financial_pricing_items", ["company_id", "is_active"])
    op.create_table(
        "financial_pricing_item_versions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("pricing_item_id", sa.Integer(), sa.ForeignKey("financial_pricing_items.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("company_unit_price", sa.Numeric(18, 3), nullable=False),
        sa.Column("mfec_share_type", sa.String(20), nullable=False),
        sa.Column("mfec_share_value", sa.Numeric(18, 3), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date()),
        sa.Column("notes", sa.Text()),
        sa.Column("created_by", sa.String(200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint("mfec_share_type IN ('fixed','percentage')", name="ck_fin_pricing_share_type"),
        sa.UniqueConstraint("pricing_item_id", "version", name="uq_fin_pricing_item_version"),
    )
    op.create_index("ix_fin_pricing_version_effective", "financial_pricing_item_versions", ["pricing_item_id", "effective_from", "effective_to"])
    op.create_table(
        "financial_member_account_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("account_id", sa.Integer(), sa.ForeignKey("financial_member_company_accounts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("pricing_item_id", sa.Integer(), sa.ForeignKey("financial_pricing_items.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("unit_price_override", sa.Numeric(18, 3)),
        sa.Column("mfec_share_type_override", sa.String(20)),
        sa.Column("mfec_share_value_override", sa.Numeric(18, 3)),
        sa.Column("started_at", sa.Date()), sa.Column("ended_at", sa.Date()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("notes", sa.Text()),
        sa.UniqueConstraint("account_id", "pricing_item_id", name="uq_fin_member_account_item"),
    )
    op.create_index("ix_fin_member_account_item_active", "financial_member_account_items", ["account_id", "is_active"])
    op.create_index("ix_fin_member_account_item_pricing", "financial_member_account_items", ["pricing_item_id"])

    def document_table(name, owner, fk, extra=()):
        op.create_table(
            name, sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(owner, sa.Integer(), sa.ForeignKey(fk, ondelete="CASCADE"), nullable=False),
            sa.Column("object_key", sa.String(500), nullable=False),
            sa.Column("original_filename", sa.String(255), nullable=False),
            sa.Column("mime_type", sa.String(120), nullable=False),
            sa.Column("size_bytes", sa.Integer(), nullable=False),
            sa.Column("uploaded_by", sa.String(200), nullable=False),
            sa.Column("uploaded_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("deleted_at", sa.DateTime(timezone=True)), sa.Column("deleted_by", sa.String(200)),
            *extra,
        )
    document_table("financial_member_annexes", "account_id", "financial_member_company_accounts.id", (
        sa.Column("signed_at", sa.Date()),
        sa.Column("replaced_annex_id", sa.Integer(), sa.ForeignKey("financial_member_annexes.id", ondelete="SET NULL")),
    ))
    op.create_index("ix_fin_member_annex_account", "financial_member_annexes", ["account_id", "deleted_at"])

    op.create_table(
        "financial_monthly_statements",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("financial_companies.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("accounting_year", sa.Integer(), nullable=False), sa.Column("accounting_month", sa.Integer(), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False), sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("received_at", sa.Date()), sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("notes", sa.Text()), sa.Column("entered_by", sa.String(200), nullable=False),
        sa.Column("approved_by", sa.String(200)), sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("reopened_by", sa.String(200)), sa.Column("reopened_at", sa.DateTime(timezone=True)),
        sa.Column("reopen_reason", sa.Text()), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("company_id", "accounting_year", "accounting_month", name="uq_fin_statement_company_month"),
    )
    op.create_index("ix_fin_statement_company_period", "financial_monthly_statements", ["company_id", "accounting_year", "accounting_month", "status"])
    op.create_index("ix_fin_statement_dates", "financial_monthly_statements", ["period_start", "period_end"])
    document_table("financial_statement_attachments", "statement_id", "financial_monthly_statements.id", (
        sa.Column("replaced_attachment_id", sa.Integer(), sa.ForeignKey("financial_statement_attachments.id", ondelete="SET NULL")),
    ))

    op.create_table(
        "financial_monthly_entry_lines",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("statement_id", sa.Integer(), sa.ForeignKey("financial_monthly_statements.id", ondelete="CASCADE"), nullable=False),
        sa.Column("member_id", sa.Integer(), sa.ForeignKey("registrations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("member_company_account_id", sa.Integer(), sa.ForeignKey("financial_member_company_accounts.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("pricing_item_id", sa.Integer(), sa.ForeignKey("financial_pricing_items.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("pricing_item_version_id", sa.Integer(), sa.ForeignKey("financial_pricing_item_versions.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("quantity", sa.Numeric(18, 3), nullable=False), sa.Column("unit_snapshot", sa.String(80), nullable=False),
        sa.Column("company_unit_price_snapshot", sa.Numeric(18, 3), nullable=False),
        sa.Column("mfec_share_type_snapshot", sa.String(20), nullable=False),
        sa.Column("mfec_share_value_snapshot", sa.Numeric(18, 3), nullable=False),
        sa.Column("gross_business_amount", sa.Numeric(18, 3), nullable=False),
        sa.Column("mfec_due_amount", sa.Numeric(18, 3), nullable=False),
        sa.Column("settlement_status", sa.String(20), nullable=False, server_default="unsettled"),
        sa.Column("entered_by", sa.String(200), nullable=False), sa.Column("updated_by", sa.String(200), nullable=False),
        sa.Column("excluded_at", sa.DateTime(timezone=True)), sa.Column("excluded_by", sa.String(200)),
        sa.Column("exclusion_reason", sa.Text()), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("statement_id", "member_company_account_id", "pricing_item_id", name="uq_fin_statement_account_item"),
    )
    op.create_index("ix_fin_entry_statement_status", "financial_monthly_entry_lines", ["statement_id", "settlement_status"])
    op.create_index("ix_fin_entry_member", "financial_monthly_entry_lines", ["member_id"])
    op.create_index("ix_fin_entry_pricing", "financial_monthly_entry_lines", ["pricing_item_id"])

    op.create_table(
        "financial_settlement_batches",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("batch_number", sa.String(40), nullable=False, unique=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("financial_companies.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("settled_at", sa.Date(), nullable=False), sa.Column("reference_number", sa.String(120)),
        sa.Column("notes", sa.Text()), sa.Column("attachment_key", sa.String(500)),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("created_by", sa.String(200), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_fin_settlement_company_date", "financial_settlement_batches", ["company_id", "settled_at", "status"])
    op.create_table(
        "financial_settlement_lines",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("batch_id", sa.Integer(), sa.ForeignKey("financial_settlement_batches.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("entry_line_id", sa.Integer(), sa.ForeignKey("financial_monthly_entry_lines.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("amount_snapshot", sa.Numeric(18, 3), nullable=False),
        sa.UniqueConstraint("batch_id", "entry_line_id", name="uq_fin_settlement_batch_line"),
    )
    op.create_table(
        "financial_settlement_reversals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("batch_id", sa.Integer(), sa.ForeignKey("financial_settlement_batches.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False), sa.Column("reversed_by", sa.String(200), nullable=False),
        sa.Column("reversed_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "financial_revenue_receipts",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("receipt_number", sa.String(80), nullable=False, unique=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("financial_companies.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("received_at", sa.Date(), nullable=False), sa.Column("amount", sa.Numeric(18, 3), nullable=False),
        sa.Column("receipt_method", sa.String(80), nullable=False), sa.Column("category", sa.String(120)),
        sa.Column("description", sa.String(500), nullable=False), sa.Column("period_start", sa.Date()), sa.Column("period_end", sa.Date()),
        sa.Column("notes", sa.Text()), sa.Column("attachment_key", sa.String(500)),
        sa.Column("created_by", sa.String(200), nullable=False), sa.Column("updated_by", sa.String(200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(timezone=True)), sa.Column("deleted_by", sa.String(200)),
        sa.Column("restored_at", sa.DateTime(timezone=True)), sa.Column("restored_by", sa.String(200)),
    )
    op.create_index("ix_fin_receipt_company_date", "financial_revenue_receipts", ["company_id", "received_at", "deleted_at"])
    op.create_table(
        "financial_receipt_allocations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("receipt_id", sa.Integer(), sa.ForeignKey("financial_revenue_receipts.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("statement_id", sa.Integer(), sa.ForeignKey("financial_monthly_statements.id", ondelete="RESTRICT")),
        sa.Column("settlement_batch_id", sa.Integer(), sa.ForeignKey("financial_settlement_batches.id", ondelete="RESTRICT")),
        sa.Column("allocated_amount", sa.Numeric(18, 3), nullable=False),
        sa.Column("created_by", sa.String(200), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint(
            "(statement_id IS NOT NULL AND settlement_batch_id IS NULL) OR "
            "(statement_id IS NULL AND settlement_batch_id IS NOT NULL)",
            name="ck_fin_allocation_one_target",
        ),
    )
    op.create_index("ix_fin_allocation_receipt", "financial_receipt_allocations", ["receipt_id"])

    # Safe legacy bridge: one default pricing item/version per existing company.
    op.execute("""
      INSERT INTO financial_pricing_items (company_id, name, unit, is_active, notes)
      SELECT c.id, 'عملية', 'طلب', TRUE, 'بند مرحّل تلقائيًا من العقد السابق'
      FROM financial_companies c
      WHERE NOT EXISTS (SELECT 1 FROM financial_pricing_items p WHERE p.company_id=c.id)
    """)
    op.execute("""
      INSERT INTO financial_pricing_item_versions
        (pricing_item_id, version, company_unit_price, mfec_share_type, mfec_share_value, effective_from, created_by, notes)
      SELECT p.id, 1, 0,
        CASE WHEN ct.commission_method='percentage' THEN 'percentage' ELSE 'fixed' END,
        ct.commission_value, ct.effective_from, 'migration', 'مرحّل من عقد العمولة السابق'
      FROM financial_pricing_items p
      JOIN financial_company_contracts ct ON ct.company_id=p.company_id
      WHERE ct.version=(SELECT MAX(ct2.version) FROM financial_company_contracts ct2 WHERE ct2.company_id=ct.company_id)
      AND NOT EXISTS (SELECT 1 FROM financial_pricing_item_versions v WHERE v.pricing_item_id=p.id)
    """)
    op.execute("""
      INSERT INTO financial_member_account_items
        (account_id, pricing_item_id, is_active, notes)
      SELECT a.id, p.id, TRUE, 'ربط مرحّل تلقائيًا'
      FROM financial_member_company_accounts a
      JOIN financial_pricing_items p ON p.company_id=a.company_id
      WHERE NOT EXISTS (
        SELECT 1 FROM financial_member_account_items ai
        WHERE ai.account_id=a.id AND ai.pricing_item_id=p.id
      )
    """)
    op.execute("""
      INSERT INTO financial_monthly_statements
        (company_id, accounting_year, accounting_month, period_start, period_end,
         status, entered_by, approved_by, approved_at, created_at, updated_at)
      SELECT p.company_id, p.accounting_year, p.accounting_month,
        make_date(p.accounting_year, p.accounting_month, 1),
        (make_date(p.accounting_year, p.accounting_month, 1)
          + INTERVAL '1 month' - INTERVAL '1 day')::date,
        CASE WHEN p.status IN ('complete','closed') THEN 'approved' ELSE 'draft' END,
        COALESCE(p.approved_by, 'migration'), p.approved_by, p.approved_at,
        COALESCE(p.created_at, CURRENT_TIMESTAMP), COALESCE(p.updated_at, CURRENT_TIMESTAMP)
      FROM financial_accounting_periods p
      WHERE NOT EXISTS (
        SELECT 1 FROM financial_monthly_statements s
        WHERE s.company_id=p.company_id AND s.accounting_year=p.accounting_year
          AND s.accounting_month=p.accounting_month
      )
    """)
    op.execute("""
      INSERT INTO financial_monthly_entry_lines
        (statement_id, member_id, member_company_account_id, pricing_item_id,
         pricing_item_version_id, quantity, unit_snapshot, company_unit_price_snapshot,
         mfec_share_type_snapshot, mfec_share_value_snapshot, gross_business_amount,
         mfec_due_amount, settlement_status, entered_by, updated_by, created_at, updated_at)
      SELECT s.id, a.member_id, ma.id, pi.id, pv.id, a.operation_count, 'طلب',
        CASE WHEN a.operation_count > 0 THEN a.gross_business_value / a.operation_count ELSE 0 END,
        CASE WHEN a.commission_method_snapshot='percentage' THEN 'percentage' ELSE 'fixed' END,
        a.commission_value_snapshot, a.gross_business_value, a.revenue_amount,
        'unsettled', a.entered_by, a.updated_by, a.created_at, a.updated_at
      FROM financial_monthly_activities a
      JOIN financial_accounting_periods p ON p.id=a.period_id
      JOIN financial_monthly_statements s ON s.company_id=p.company_id
        AND s.accounting_year=p.accounting_year AND s.accounting_month=p.accounting_month
      JOIN financial_member_company_accounts ma ON ma.member_id=a.member_id AND ma.company_id=a.company_id
      JOIN financial_pricing_items pi ON pi.company_id=a.company_id
      JOIN financial_pricing_item_versions pv ON pv.pricing_item_id=pi.id AND pv.version=1
      WHERE NOT EXISTS (
        SELECT 1 FROM financial_monthly_entry_lines l
        WHERE l.statement_id=s.id AND l.member_company_account_id=ma.id AND l.pricing_item_id=pi.id
      )
    """)


def downgrade():
    # Production policy is forward-only/additive. Downgrade intentionally keeps data.
    pass
