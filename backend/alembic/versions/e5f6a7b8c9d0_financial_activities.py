"""additive financial and activities module

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, Sequence[str], None] = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "financial_service_types",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False, unique=True),
        sa.Column("code", sa.String(64), nullable=False, unique=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "financial_companies",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False, unique=True),
        sa.Column("service_type_id", sa.Integer(), sa.ForeignKey("financial_service_types.id"), nullable=False),
        sa.Column("contact_info", sa.Text()), sa.Column("status", sa.String(20), nullable=False),
        sa.Column("contract_start", sa.Date()), sa.Column("contract_end", sa.Date()),
        sa.Column("notes", sa.Text()), sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_financial_companies_service_status", "financial_companies", ["service_type_id", "status"])
    op.create_table(
        "financial_company_contracts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("financial_companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("commission_method", sa.String(40), nullable=False),
        sa.Column("commission_value", sa.Numeric(18, 3), nullable=False),
        sa.Column("custom_config", sa.Text()), sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date()), sa.Column("attachment_key", sa.String(500)),
        sa.Column("notes", sa.Text()), sa.Column("created_by", sa.String(200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("company_id", "version", name="uq_fin_company_contract_version"),
    )
    op.create_index("ix_fin_contract_effective", "financial_company_contracts", ["company_id", "effective_from", "effective_to"])
    op.create_table(
        "financial_member_company_accounts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("member_id", sa.Integer(), sa.ForeignKey("registrations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("financial_companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("registered_name", sa.String(200)), sa.Column("registered_phone", sa.String(50)),
        sa.Column("customer_code", sa.String(100)), sa.Column("statement_url", sa.Text()),
        sa.Column("notes", sa.Text()), sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True)), sa.Column("updated_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("member_id", "company_id", name="uq_fin_member_company"),
    )
    op.create_index("ix_fin_account_company_active", "financial_member_company_accounts", ["company_id", "is_active"])
    op.create_index("ix_fin_account_member", "financial_member_company_accounts", ["member_id"])
    op.create_table(
        "financial_accounting_periods",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("financial_companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("accounting_year", sa.Integer(), nullable=False), sa.Column("accounting_month", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False), sa.Column("approved_by", sa.String(200)),
        sa.Column("approved_at", sa.DateTime(timezone=True)), sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("company_id", "accounting_year", "accounting_month", name="uq_fin_period"),
    )
    op.create_index("ix_fin_period_year_month", "financial_accounting_periods", ["accounting_year", "accounting_month", "status"])
    op.create_table(
        "financial_monthly_activities",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("period_id", sa.Integer(), sa.ForeignKey("financial_accounting_periods.id", ondelete="CASCADE"), nullable=False),
        sa.Column("member_id", sa.Integer(), sa.ForeignKey("registrations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("financial_companies.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("service_type_id", sa.Integer(), sa.ForeignKey("financial_service_types.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("operation_count", sa.Integer(), nullable=False), sa.Column("gross_business_value", sa.Numeric(18, 3), nullable=False),
        sa.Column("commission_method_snapshot", sa.String(40), nullable=False),
        sa.Column("commission_value_snapshot", sa.Numeric(18, 3), nullable=False),
        sa.Column("revenue_amount", sa.Numeric(18, 3), nullable=False),
        sa.Column("entered_by", sa.String(200), nullable=False), sa.Column("updated_by", sa.String(200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True)), sa.Column("updated_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("period_id", "member_id", name="uq_fin_monthly_period_member"),
    )
    op.create_index("ix_fin_activity_member", "financial_monthly_activities", ["member_id"])
    op.create_index("ix_fin_activity_company", "financial_monthly_activities", ["company_id"])
    op.create_index("ix_fin_activity_service", "financial_monthly_activities", ["service_type_id"])
    op.create_table(
        "financial_expenses",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("expense_date", sa.Date(), nullable=False),
        sa.Column("accounting_year", sa.Integer(), nullable=False), sa.Column("accounting_month", sa.Integer(), nullable=False),
        sa.Column("category", sa.String(120), nullable=False), sa.Column("description", sa.String(500), nullable=False),
        sa.Column("amount", sa.Numeric(18, 3), nullable=False), sa.Column("notes", sa.Text()),
        sa.Column("receipt_key", sa.String(500)), sa.Column("created_by", sa.String(200), nullable=False),
        sa.Column("updated_by", sa.String(200), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_fin_expense_year_month", "financial_expenses", ["accounting_year", "accounting_month"])
    op.create_table(
        "financial_distinguished_members",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("accounting_year", sa.Integer(), nullable=False),
        sa.Column("accounting_month", sa.Integer(), nullable=False),
        sa.Column("member_id", sa.Integer(), sa.ForeignKey("registrations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("ranking_basis", sa.String(30), nullable=False), sa.Column("confirmed_by", sa.String(200), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("accounting_year", "accounting_month", name="uq_fin_winner_month"),
    )
    op.create_table(
        "financial_member_certificates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("winner_id", sa.Integer(), sa.ForeignKey("financial_distinguished_members.id", ondelete="CASCADE"), nullable=False),
        sa.Column("member_id", sa.Integer(), sa.ForeignKey("registrations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("certificate_number", sa.String(80), nullable=False, unique=True),
        sa.Column("file_key", sa.String(500)), sa.Column("issued_by", sa.String(200), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "financial_audit_logs",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("action", sa.String(100), nullable=False),
        sa.Column("entity_type", sa.String(80), nullable=False), sa.Column("entity_id", sa.Integer()),
        sa.Column("actor", sa.String(200), nullable=False), sa.Column("old_values", sa.Text()),
        sa.Column("new_values", sa.Text()), sa.Column("created_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_fin_audit_created_action", "financial_audit_logs", ["created_at", "action"])
    op.execute(
        """
        INSERT INTO financial_service_types (name, code, is_active, created_at)
        VALUES
          ('شركة شحن', 'shipping', TRUE, CURRENT_TIMESTAMP),
          ('شركة توصيل', 'delivery', TRUE, CURRENT_TIMESTAMP),
          ('برمجة تطبيقات', 'software', TRUE, CURRENT_TIMESTAMP),
          ('ترويج وإدارة صفحات', 'marketing', TRUE, CURRENT_TIMESTAMP),
          ('فرز بضائع', 'sorting', TRUE, CURRENT_TIMESTAMP),
          ('خدمات أخرى', 'other', TRUE, CURRENT_TIMESTAMP)
        """
    )


def downgrade() -> None:
    for table in (
        "financial_audit_logs", "financial_member_certificates", "financial_distinguished_members",
        "financial_expenses", "financial_monthly_activities", "financial_accounting_periods",
        "financial_member_company_accounts", "financial_company_contracts",
        "financial_companies", "financial_service_types",
    ):
        op.drop_table(table)
