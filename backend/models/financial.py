"""Additive financial/activity models.

Members are always referenced from ``registrations``; this module never copies
membership identity data.
"""
from datetime import datetime

from sqlalchemy import (
    Boolean,
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
    expense_date = Column(Date, nullable=False)
    accounting_year = Column(Integer, nullable=False)
    accounting_month = Column(Integer, nullable=False)
    category = Column(String(120), nullable=False)
    description = Column(String(500), nullable=False)
    amount = Column(Numeric(18, 3), nullable=False)
    notes = Column(Text)
    receipt_key = Column(String(500))
    created_by = Column(String(200), nullable=False)
    updated_by = Column(String(200), nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)
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
