"""Additive financial/activity models.

Members are always referenced from ``registrations``; this module never copies
membership identity data.
"""
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)

from core.database import Base


class ServiceType(Base):
    __tablename__ = "financial_service_types"
    id = Column(Integer, primary_key=True)
    name = Column(String(120), unique=True, nullable=False)
    code = Column(String(64), unique=True, nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    default_commission_method = Column(String(40))
    default_commission_value = Column(Numeric(18, 3))
    created_at = Column(DateTime(timezone=True), default=datetime.now)


class FinancialCompany(Base):
    __tablename__ = "financial_companies"
    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False, unique=True)
    service_type_id = Column(Integer, ForeignKey("financial_service_types.id"), nullable=False)
    contact_info = Column(Text)
    status = Column(String(20), nullable=False, default="active")
    contract_start = Column(Date)
    contract_end = Column(Date)
    notes = Column(Text)
    owner_name = Column(String(200))
    address = Column(Text)
    mobile = Column(String(50))
    cooperation_status = Column(String(20), nullable=False, default="active")
    cooperation_started_at = Column(Date)
    deleted_at = Column(DateTime(timezone=True))
    deleted_by = Column(String(200))
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)
    __table_args__ = (Index("ix_financial_companies_service_status", "service_type_id", "status"),)


class CompanyContract(Base):
    __tablename__ = "financial_company_contracts"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("financial_companies.id", ondelete="CASCADE"), nullable=False)
    version = Column(Integer, nullable=False, default=1)
    commission_method = Column(String(40), nullable=False)
    commission_value = Column(Numeric(18, 3), nullable=False, default=0)
    custom_config = Column(Text)
    effective_from = Column(Date, nullable=False)
    effective_to = Column(Date)
    attachment_key = Column(String(500))
    notes = Column(Text)
    created_by = Column(String(200), nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    __table_args__ = (
        UniqueConstraint("company_id", "version", name="uq_fin_company_contract_version"),
        Index("ix_fin_contract_effective", "company_id", "effective_from", "effective_to"),
    )


class MemberCompanyAccount(Base):
    __tablename__ = "financial_member_company_accounts"
    id = Column(Integer, primary_key=True)
    member_id = Column(Integer, ForeignKey("registrations.id", ondelete="RESTRICT"), nullable=False)
    company_id = Column(Integer, ForeignKey("financial_companies.id", ondelete="CASCADE"), nullable=False)
    registered_name = Column(String(200))
    registered_phone = Column(String(50))
    customer_code = Column(String(100))
    statement_url = Column(Text)
    customer_portal_url = Column(Text)
    started_at = Column(Date)
    ended_at = Column(Date)
    status = Column(String(20), nullable=False, default="active")
    default_unit_price_override = Column(Numeric(18, 3))
    default_mfec_share_type_override = Column(String(20))
    default_mfec_share_value_override = Column(Numeric(18, 3))
    deleted_at = Column(DateTime(timezone=True))
    deleted_by = Column(String(200))
    notes = Column(Text)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)
    __table_args__ = (
        UniqueConstraint("member_id", "company_id", name="uq_fin_member_company"),
        Index("ix_fin_account_company_active", "company_id", "is_active"),
        Index("ix_fin_account_member", "member_id"),
    )


class AccountingPeriod(Base):
    __tablename__ = "financial_accounting_periods"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("financial_companies.id", ondelete="CASCADE"), nullable=False)
    accounting_year = Column(Integer, nullable=False)
    accounting_month = Column(Integer, nullable=False)
    status = Column(String(20), nullable=False, default="not_started")
    approved_by = Column(String(200))
    approved_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)
    __table_args__ = (
        UniqueConstraint("company_id", "accounting_year", "accounting_month", name="uq_fin_period"),
        Index("ix_fin_period_year_month", "accounting_year", "accounting_month", "status"),
    )


class MonthlyActivity(Base):
    __tablename__ = "financial_monthly_activities"
    id = Column(Integer, primary_key=True)
    period_id = Column(Integer, ForeignKey("financial_accounting_periods.id", ondelete="CASCADE"), nullable=False)
    member_id = Column(Integer, ForeignKey("registrations.id", ondelete="RESTRICT"), nullable=False)
    company_id = Column(Integer, ForeignKey("financial_companies.id", ondelete="RESTRICT"), nullable=False)
    service_type_id = Column(Integer, ForeignKey("financial_service_types.id", ondelete="RESTRICT"), nullable=False)
    operation_count = Column(Integer, nullable=False, default=0)
    gross_business_value = Column(Numeric(18, 3), nullable=False, default=0)
    commission_method_snapshot = Column(String(40), nullable=False)
    commission_value_snapshot = Column(Numeric(18, 3), nullable=False)
    revenue_amount = Column(Numeric(18, 3), nullable=False, default=0)
    entered_by = Column(String(200), nullable=False)
    updated_by = Column(String(200), nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)
    __table_args__ = (
        UniqueConstraint("period_id", "member_id", name="uq_fin_monthly_period_member"),
        Index("ix_fin_activity_member", "member_id"),
        Index("ix_fin_activity_company", "company_id"),
        Index("ix_fin_activity_service", "service_type_id"),
    )


class FinancialExpense(Base):
    __tablename__ = "financial_expenses"
    id = Column(Integer, primary_key=True)
    payment_number = Column(String(80), unique=True)
    expense_date = Column(Date, nullable=False)
    accounting_year = Column(Integer, nullable=False)
    accounting_month = Column(Integer, nullable=False)
    payee = Column(String(200))  # دُفع إلى
    person_name = Column(String(200))  # اسم الشخص
    company_name = Column(String(200))  # اسم الشركة (المستفيدة)
    payment_method = Column(String(80))
    category = Column(String(120), nullable=False)
    description = Column(String(500), nullable=False)
    amount = Column(Numeric(18, 3), nullable=False)
    notes = Column(Text)
    receipt_key = Column(String(500))
    created_by = Column(String(200), nullable=False)
    updated_by = Column(String(200), nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)
    deleted_at = Column(DateTime(timezone=True))
    deleted_by = Column(String(200))
    restored_at = Column(DateTime(timezone=True))
    restored_by = Column(String(200))
    __table_args__ = (Index("ix_fin_expense_year_month", "accounting_year", "accounting_month"),)


class DistinguishedMember(Base):
    __tablename__ = "financial_distinguished_members"
    id = Column(Integer, primary_key=True)
    accounting_year = Column(Integer, nullable=False)
    accounting_month = Column(Integer, nullable=False)
    member_id = Column(Integer, ForeignKey("registrations.id", ondelete="RESTRICT"), nullable=False)
    ranking_basis = Column(String(30), nullable=False)
    confirmed_by = Column(String(200), nullable=False)
    confirmed_at = Column(DateTime(timezone=True), default=datetime.now)
    __table_args__ = (UniqueConstraint("accounting_year", "accounting_month", name="uq_fin_winner_month"),)


class MemberCertificate(Base):
    __tablename__ = "financial_member_certificates"
    id = Column(Integer, primary_key=True)
    winner_id = Column(Integer, ForeignKey("financial_distinguished_members.id", ondelete="CASCADE"), nullable=False)
    member_id = Column(Integer, ForeignKey("registrations.id", ondelete="RESTRICT"), nullable=False)
    certificate_number = Column(String(80), nullable=False, unique=True)
    file_key = Column(String(500))
    issued_by = Column(String(200), nullable=False)
    issued_at = Column(DateTime(timezone=True), default=datetime.now)


class FinancialAuditLog(Base):
    __tablename__ = "financial_audit_logs"
    id = Column(Integer, primary_key=True)
    action = Column(String(100), nullable=False)
    entity_type = Column(String(80), nullable=False)
    entity_id = Column(Integer)
    actor = Column(String(200), nullable=False)
    old_values = Column(Text)
    new_values = Column(Text)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    __table_args__ = (Index("ix_fin_audit_created_action", "created_at", "action"),)


class CompanyAttachment(Base):
    __tablename__ = "financial_company_attachments"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("financial_companies.id", ondelete="CASCADE"), nullable=False)
    contract_id = Column(Integer, ForeignKey("financial_company_contracts.id", ondelete="SET NULL"))
    document_type = Column(String(40), nullable=False, default="contract")
    object_key = Column(String(500), nullable=False)
    original_filename = Column(String(255), nullable=False)
    mime_type = Column(String(120), nullable=False)
    size_bytes = Column(Integer, nullable=False)
    uploaded_by = Column(String(200), nullable=False)
    uploaded_at = Column(DateTime(timezone=True), default=datetime.now)
    replaced_attachment_id = Column(Integer, ForeignKey("financial_company_attachments.id", ondelete="SET NULL"))
    deleted_at = Column(DateTime(timezone=True))
    deleted_by = Column(String(200))
    __table_args__ = (Index("ix_fin_company_attachment_company", "company_id", "deleted_at"),)


class PricingItem(Base):
    __tablename__ = "financial_pricing_items"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("financial_companies.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(160), nullable=False)
    unit = Column(String(80), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    notes = Column(Text)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    deleted_at = Column(DateTime(timezone=True))
    deleted_by = Column(String(200))
    __table_args__ = (
        UniqueConstraint("company_id", "name", name="uq_fin_pricing_item_company_name"),
        Index("ix_fin_pricing_item_company_active", "company_id", "is_active"),
    )


class PricingItemVersion(Base):
    __tablename__ = "financial_pricing_item_versions"
    id = Column(Integer, primary_key=True)
    pricing_item_id = Column(Integer, ForeignKey("financial_pricing_items.id", ondelete="CASCADE"), nullable=False)
    version = Column(Integer, nullable=False)
    company_unit_price = Column(Numeric(18, 3), nullable=False, default=0)
    mfec_share_type = Column(String(20), nullable=False)
    mfec_share_value = Column(Numeric(18, 3), nullable=False, default=0)
    effective_from = Column(Date, nullable=False)
    effective_to = Column(Date)
    notes = Column(Text)
    created_by = Column(String(200), nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    __table_args__ = (
        UniqueConstraint("pricing_item_id", "version", name="uq_fin_pricing_item_version"),
        CheckConstraint("mfec_share_type IN ('fixed','percentage')", name="ck_fin_pricing_share_type"),
        Index("ix_fin_pricing_version_effective", "pricing_item_id", "effective_from", "effective_to"),
    )


class MemberAccountItem(Base):
    __tablename__ = "financial_member_account_items"
    id = Column(Integer, primary_key=True)
    account_id = Column(Integer, ForeignKey("financial_member_company_accounts.id", ondelete="CASCADE"), nullable=False)
    pricing_item_id = Column(Integer, ForeignKey("financial_pricing_items.id", ondelete="RESTRICT"), nullable=False)
    unit_price_override = Column(Numeric(18, 3))
    mfec_share_type_override = Column(String(20))
    mfec_share_value_override = Column(Numeric(18, 3))
    started_at = Column(Date)
    ended_at = Column(Date)
    is_active = Column(Boolean, nullable=False, default=True)
    notes = Column(Text)
    __table_args__ = (
        UniqueConstraint("account_id", "pricing_item_id", name="uq_fin_member_account_item"),
        Index("ix_fin_member_account_item_active", "account_id", "is_active"),
        Index("ix_fin_member_account_item_pricing", "pricing_item_id"),
    )


class MemberAnnex(Base):
    __tablename__ = "financial_member_annexes"
    id = Column(Integer, primary_key=True)
    account_id = Column(Integer, ForeignKey("financial_member_company_accounts.id", ondelete="CASCADE"), nullable=False)
    object_key = Column(String(500), nullable=False)
    original_filename = Column(String(255), nullable=False)
    mime_type = Column(String(120), nullable=False)
    size_bytes = Column(Integer, nullable=False)
    signed_at = Column(Date)
    uploaded_by = Column(String(200), nullable=False)
    uploaded_at = Column(DateTime(timezone=True), default=datetime.now)
    replaced_annex_id = Column(Integer, ForeignKey("financial_member_annexes.id", ondelete="SET NULL"))
    deleted_at = Column(DateTime(timezone=True))
    deleted_by = Column(String(200))
    __table_args__ = (Index("ix_fin_member_annex_account", "account_id", "deleted_at"),)


class MonthlyStatement(Base):
    __tablename__ = "financial_monthly_statements"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("financial_companies.id", ondelete="RESTRICT"), nullable=False)
    accounting_year = Column(Integer, nullable=False)
    accounting_month = Column(Integer, nullable=False)
    period_start = Column(Date, nullable=False)
    period_end = Column(Date, nullable=False)
    received_at = Column(Date)
    status = Column(String(20), nullable=False, default="draft")
    notes = Column(Text)
    entered_by = Column(String(200), nullable=False)
    approved_by = Column(String(200))
    approved_at = Column(DateTime(timezone=True))
    reopened_by = Column(String(200))
    reopened_at = Column(DateTime(timezone=True))
    reopen_reason = Column(Text)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)
    __table_args__ = (
        UniqueConstraint("company_id", "accounting_year", "accounting_month", name="uq_fin_statement_company_month"),
        Index("ix_fin_statement_company_period", "company_id", "accounting_year", "accounting_month", "status"),
        Index("ix_fin_statement_dates", "period_start", "period_end"),
    )


class StatementAttachment(Base):
    __tablename__ = "financial_statement_attachments"
    id = Column(Integer, primary_key=True)
    statement_id = Column(Integer, ForeignKey("financial_monthly_statements.id", ondelete="CASCADE"), nullable=False)
    object_key = Column(String(500), nullable=False)
    original_filename = Column(String(255), nullable=False)
    mime_type = Column(String(120), nullable=False)
    size_bytes = Column(Integer, nullable=False)
    uploaded_by = Column(String(200), nullable=False)
    uploaded_at = Column(DateTime(timezone=True), default=datetime.now)
    replaced_attachment_id = Column(Integer, ForeignKey("financial_statement_attachments.id", ondelete="SET NULL"))
    deleted_at = Column(DateTime(timezone=True))
    deleted_by = Column(String(200))


class MonthlyEntryLine(Base):
    __tablename__ = "financial_monthly_entry_lines"
    id = Column(Integer, primary_key=True)
    statement_id = Column(Integer, ForeignKey("financial_monthly_statements.id", ondelete="CASCADE"), nullable=False)
    member_id = Column(Integer, ForeignKey("registrations.id", ondelete="RESTRICT"), nullable=False)
    member_company_account_id = Column(Integer, ForeignKey("financial_member_company_accounts.id", ondelete="RESTRICT"), nullable=False)
    pricing_item_id = Column(Integer, ForeignKey("financial_pricing_items.id", ondelete="RESTRICT"), nullable=False)
    pricing_item_version_id = Column(Integer, ForeignKey("financial_pricing_item_versions.id", ondelete="RESTRICT"), nullable=False)
    quantity = Column(Numeric(18, 3), nullable=False, default=0)
    unit_snapshot = Column(String(80), nullable=False)
    company_unit_price_snapshot = Column(Numeric(18, 3), nullable=False)
    mfec_share_type_snapshot = Column(String(20), nullable=False)
    mfec_share_value_snapshot = Column(Numeric(18, 3), nullable=False)
    gross_business_amount = Column(Numeric(18, 3), nullable=False)
    mfec_due_amount = Column(Numeric(18, 3), nullable=False)
    settlement_status = Column(String(20), nullable=False, default="unsettled")
    entered_by = Column(String(200), nullable=False)
    updated_by = Column(String(200), nullable=False)
    excluded_at = Column(DateTime(timezone=True))
    excluded_by = Column(String(200))
    exclusion_reason = Column(Text)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)
    __table_args__ = (
        UniqueConstraint("statement_id", "member_company_account_id", "pricing_item_id", name="uq_fin_statement_account_item"),
        Index("ix_fin_entry_statement_status", "statement_id", "settlement_status"),
        Index("ix_fin_entry_member", "member_id"),
        Index("ix_fin_entry_pricing", "pricing_item_id"),
    )


class SettlementBatch(Base):
    __tablename__ = "financial_settlement_batches"
    id = Column(Integer, primary_key=True)
    batch_number = Column(String(40), nullable=False, unique=True)
    company_id = Column(Integer, ForeignKey("financial_companies.id", ondelete="RESTRICT"), nullable=False)
    settled_at = Column(Date, nullable=False)
    reference_number = Column(String(120))
    notes = Column(Text)
    attachment_key = Column(String(500))
    status = Column(String(20), nullable=False, default="active")
    created_by = Column(String(200), nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    __table_args__ = (Index("ix_fin_settlement_company_date", "company_id", "settled_at", "status"),)


class SettlementLine(Base):
    __tablename__ = "financial_settlement_lines"
    id = Column(Integer, primary_key=True)
    batch_id = Column(Integer, ForeignKey("financial_settlement_batches.id", ondelete="RESTRICT"), nullable=False)
    entry_line_id = Column(Integer, ForeignKey("financial_monthly_entry_lines.id", ondelete="RESTRICT"), nullable=False)
    amount_snapshot = Column(Numeric(18, 3), nullable=False)
    __table_args__ = (UniqueConstraint("batch_id", "entry_line_id", name="uq_fin_settlement_batch_line"),)


class SettlementReversal(Base):
    __tablename__ = "financial_settlement_reversals"
    id = Column(Integer, primary_key=True)
    batch_id = Column(Integer, ForeignKey("financial_settlement_batches.id", ondelete="RESTRICT"), nullable=False)
    reason = Column(Text, nullable=False)
    reversed_by = Column(String(200), nullable=False)
    reversed_at = Column(DateTime(timezone=True), default=datetime.now)


class RevenueReceipt(Base):
    __tablename__ = "financial_revenue_receipts"
    id = Column(Integer, primary_key=True)
    receipt_number = Column(String(80), nullable=False, unique=True)
    company_id = Column(Integer, ForeignKey("financial_companies.id", ondelete="RESTRICT"), nullable=False)
    received_at = Column(Date, nullable=False)
    amount = Column(Numeric(18, 3), nullable=False)
    receipt_method = Column(String(80), nullable=False)
    category = Column(String(120))
    description = Column(String(500), nullable=False)
    period_start = Column(Date)
    period_end = Column(Date)
    notes = Column(Text)
    attachment_key = Column(String(500))
    created_by = Column(String(200), nullable=False)
    updated_by = Column(String(200), nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)
    deleted_at = Column(DateTime(timezone=True))
    deleted_by = Column(String(200))
    restored_at = Column(DateTime(timezone=True))
    restored_by = Column(String(200))
    __table_args__ = (Index("ix_fin_receipt_company_date", "company_id", "received_at", "deleted_at"),)


class ReceiptAllocation(Base):
    __tablename__ = "financial_receipt_allocations"
    id = Column(Integer, primary_key=True)
    receipt_id = Column(Integer, ForeignKey("financial_revenue_receipts.id", ondelete="RESTRICT"), nullable=False)
    statement_id = Column(Integer, ForeignKey("financial_monthly_statements.id", ondelete="RESTRICT"))
    settlement_batch_id = Column(Integer, ForeignKey("financial_settlement_batches.id", ondelete="RESTRICT"))
    allocated_amount = Column(Numeric(18, 3), nullable=False)
    created_by = Column(String(200), nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    __table_args__ = (
        CheckConstraint(
            "(statement_id IS NOT NULL AND settlement_batch_id IS NULL) OR "
            "(statement_id IS NULL AND settlement_batch_id IS NOT NULL)",
            name="ck_fin_allocation_one_target",
        ),
        Index("ix_fin_allocation_receipt", "receipt_id"),
    )


class FinancialBackup(Base):
    """Private logical backup artifact and audited restore-request metadata."""
    __tablename__ = "financial_backups"
    id = Column(Integer, primary_key=True)
    backup_number = Column(String(50), nullable=False, unique=True)
    object_key = Column(String(500), nullable=False)
    kind = Column(String(30), nullable=False, default="manual")
    status = Column(String(30), nullable=False, default="ready")
    notes = Column(Text)
    size_bytes = Column(Integer, nullable=False, default=0)
    checksum_sha256 = Column(String(64), nullable=False)
    created_by = Column(String(200), nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.now, nullable=False)
    restore_requested_by = Column(String(200))
    restore_requested_at = Column(DateTime(timezone=True))
    pre_restore_backup_id = Column(Integer, ForeignKey("financial_backups.id", ondelete="SET NULL"))
    deleted_at = Column(DateTime(timezone=True))
    deleted_by = Column(String(200))
    __table_args__ = (
        Index("ix_fin_backup_created_status", "created_at", "status"),
        Index("ix_fin_backup_deleted", "deleted_at"),
    )
