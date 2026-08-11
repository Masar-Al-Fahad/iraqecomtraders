"""Financial and activities administration.

All member identity fields are joined from ``registrations``. Financial rows
only store foreign keys and accounting snapshots.
"""
from __future__ import annotations

import io
import json
import logging
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, HttpUrl
from sqlalchemy import and_, case, delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from dependencies.permissions import require_any_permission, require_permission
from models.financial import (
    AccountingPeriod,
    CompanyContract,
    DistinguishedMember,
    FinancialAuditLog,
    FinancialCompany,
    FinancialExpense,
    MemberCertificate,
    MemberAccountItem,
    MemberCompanyAccount,
    MonthlyActivity,
    PricingItem,
    ServiceType,
)
from models.registrations import Registrations
from schemas.auth import UserResponse
from services.actor import resolve_actor_name
from services.financial import COMMISSION_METHODS, add_audit, build_financial_xlsx, calculate_revenue
from services import supabase_storage

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/admin/financial", tags=["financial-activities"])

FINANCIAL_VIEW_PERMS = (
    "view_revenue",
    "view_profits",
    "view_financial_reports",
    "view_statements",
    "financial.dashboard.view",
    "financial.reports.view",
    "financial.revenues.view",
    "financial.settlements.view",
)


def _iso(value: Any) -> Any:
    return value.isoformat() if hasattr(value, "isoformat") and value is not None else value


def _decimal(value: Any) -> Decimal:
    return Decimal(str(value or 0))


def _finance_allowed(user: UserResponse) -> bool:
    if getattr(user, "is_super_admin", False):
        return True
    perms = getattr(user, "permissions", {}) or {}
    return any(perms.get(key) for key in FINANCIAL_VIEW_PERMS)


class ServiceTypeIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    code: str = Field(min_length=2, max_length=64, pattern=r"^[a-z0-9_]+$")
    is_active: bool = True
    default_commission_method: Optional[str] = None
    default_commission_value: Optional[Decimal] = Field(default=None, ge=0)


class CompanyIn(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    service_type_id: int
    contact_info: Optional[str] = None
    status: Literal["active", "inactive"] = "active"
    contract_start: Optional[date] = None
    contract_end: Optional[date] = None
    notes: Optional[str] = None
    owner_name: Optional[str] = None
    address: Optional[str] = None
    mobile: Optional[str] = None
    cooperation_status: Literal["active", "suspended", "ended"] = "active"
    cooperation_started_at: Optional[date] = None


class ContractIn(BaseModel):
    commission_method: str
    commission_value: Decimal = Field(ge=0)
    custom_config: Optional[dict] = None
    effective_from: date
    effective_to: Optional[date] = None
    attachment_key: Optional[str] = None
    notes: Optional[str] = None


class AccountItemAssignmentIn(BaseModel):
    pricing_item_id: int
    unit_price_override: Optional[Decimal] = Field(default=None, ge=0)
    mfec_share_type_override: Literal["fixed", "percentage"] | None = None
    mfec_share_value_override: Optional[Decimal] = Field(default=None, ge=0)
    is_active: bool = True


class AccountIn(BaseModel):
    member_id: int
    company_id: int
    registered_name: Optional[str] = None
    registered_phone: Optional[str] = None
    customer_code: Optional[str] = None
    statement_url: Optional[HttpUrl] = None
    customer_portal_url: Optional[HttpUrl] = None
    started_at: Optional[date] = None
    ended_at: Optional[date] = None
    status: Literal["active", "inactive", "suspended"] = "active"
    default_unit_price_override: Optional[Decimal] = Field(default=None, ge=0)
    default_mfec_share_type_override: Literal["fixed", "percentage"] | None = None
    default_mfec_share_value_override: Optional[Decimal] = Field(default=None, ge=0)
    notes: Optional[str] = None
    is_active: bool = True
    items: Optional[list[AccountItemAssignmentIn]] = None


class MonthlyRowIn(BaseModel):
    member_id: int
    operation_count: int = Field(ge=0, le=10_000_000)
    gross_business_value: Decimal = Field(default=Decimal("0"), ge=0)


class MonthlyBulkIn(BaseModel):
    company_id: int
    accounting_year: int = Field(ge=2000, le=2200)
    accounting_month: int = Field(ge=1, le=12)
    rows: list[MonthlyRowIn]
    mark_complete: bool = False


class PeriodStatusIn(BaseModel):
    status: Literal["not_started", "in_progress", "complete", "closed"]


class ExpenseIn(BaseModel):
    expense_date: date
    accounting_year: int = Field(ge=2000, le=2200)
    accounting_month: int = Field(ge=1, le=12)
    category: str = Field(min_length=2, max_length=120)
    description: str = Field(min_length=2, max_length=500)
    amount: Decimal = Field(gt=0)
    notes: Optional[str] = None
    receipt_key: Optional[str] = None


class WinnerIn(BaseModel):
    accounting_year: int
    accounting_month: int
    member_id: int
    ranking_basis: Literal["operations", "revenue"]


class CertificateIn(BaseModel):
    winner_id: int
    file_key: Optional[str] = None


async def _active_contract(db: AsyncSession, company_id: int, on_date: date) -> CompanyContract:
    result = await db.execute(
        select(CompanyContract)
        .where(
            CompanyContract.company_id == company_id,
            CompanyContract.effective_from <= on_date,
            or_(CompanyContract.effective_to.is_(None), CompanyContract.effective_to >= on_date),
        )
        .order_by(CompanyContract.effective_from.desc(), CompanyContract.version.desc())
        .limit(1)
    )
    contract = result.scalar_one_or_none()
    if not contract:
        raise HTTPException(status_code=400, detail="لا يوجد عقد عمولة فعال للشركة في الشهر المحدد")
    return contract


async def _report_rows(
    db: AsyncSession,
    *,
    year: Optional[int],
    month: Optional[int],
    company_id: Optional[int],
    service_type_id: Optional[int],
    member_id: Optional[int],
    governorate: Optional[str],
) -> list[dict]:
    shipping_ops = func.sum(case((ServiceType.code == "shipping", MonthlyActivity.operation_count), else_=0))
    shipping_rev = func.sum(case((ServiceType.code == "shipping", MonthlyActivity.revenue_amount), else_=0))
    delivery_ops = func.sum(case((ServiceType.code == "delivery", MonthlyActivity.operation_count), else_=0))
    delivery_rev = func.sum(case((ServiceType.code == "delivery", MonthlyActivity.revenue_amount), else_=0))
    other_ops = func.sum(
        case((ServiceType.code.notin_(["shipping", "delivery"]), MonthlyActivity.operation_count), else_=0)
    )
    other_rev = func.sum(
        case((ServiceType.code.notin_(["shipping", "delivery"]), MonthlyActivity.revenue_amount), else_=0)
    )
    stmt = (
        select(
            Registrations.id,
            Registrations.membership_number,
            Registrations.merchant_name,
            Registrations.governorate,
            shipping_ops,
            shipping_rev,
            delivery_ops,
            delivery_rev,
            other_ops,
            other_rev,
            func.sum(MonthlyActivity.operation_count),
            func.sum(MonthlyActivity.revenue_amount),
        )
        .join(MonthlyActivity, MonthlyActivity.member_id == Registrations.id)
        .join(AccountingPeriod, AccountingPeriod.id == MonthlyActivity.period_id)
        .join(ServiceType, ServiceType.id == MonthlyActivity.service_type_id)
        .group_by(
            Registrations.id,
            Registrations.membership_number,
            Registrations.merchant_name,
            Registrations.governorate,
        )
        .order_by(func.sum(MonthlyActivity.revenue_amount).desc())
    )
    if year:
        stmt = stmt.where(AccountingPeriod.accounting_year == year)
    if month:
        stmt = stmt.where(AccountingPeriod.accounting_month == month)
    if company_id:
        stmt = stmt.where(MonthlyActivity.company_id == company_id)
    if service_type_id:
        stmt = stmt.where(MonthlyActivity.service_type_id == service_type_id)
    if member_id:
        stmt = stmt.where(Registrations.id == member_id)
    if governorate:
        stmt = stmt.where(Registrations.governorate == governorate)
    result = await db.execute(stmt)
    return [
        {
            "member_id": row[0],
            "membership_number": row[1],
            "member_name": row[2],
            "governorate": row[3],
            "shipping_operations": int(row[4] or 0),
            "shipping_revenue": float(row[5] or 0),
            "delivery_operations": int(row[6] or 0),
            "delivery_revenue": float(row[7] or 0),
            "other_operations": int(row[8] or 0),
            "other_revenue": float(row[9] or 0),
            "total_operations": int(row[10] or 0),
            "total_revenue": float(row[11] or 0),
        }
        for row in result.all()
    ]


@router.get("/access")
async def financial_access(
    current_user: UserResponse = Depends(require_any_permission(
        "monthly_entry", "view_companies", "manage_companies_contracts",
        "manage_member_company_accounts", "enter_expenses", "view_expenses",
        *FINANCIAL_VIEW_PERMS, "issue_distinguished_certificate",
        "financial.dashboard.view", "financial.companies.view", "financial.companies.create",
        "financial.companies.edit", "financial.companies.delete", "financial.contracts.manage", "financial.pricing.manage",
        "financial.member_links.view", "financial.member_links.create", "financial.member_links.edit", "financial.member_links.delete",
        "financial.annexes.manage",
        "financial.monthly.view", "financial.monthly.enter", "financial.monthly.edit",
        "financial.monthly.approve", "financial.monthly.reopen",
        "financial.expenses.view", "financial.expenses.create", "financial.expenses.edit",
        "financial.expenses.delete", "financial.expenses.restore", "financial.revenues.view",
        "financial.revenues.create", "financial.revenues.edit", "financial.revenues.delete",
        "financial.revenues.restore", "financial.settlements.view", "financial.settlements.create",
        "financial.settlements.reverse", "financial.reports.view", "financial.reports.pdf",
        "financial.reports.xlsx", "financial.reports.print", "financial.audit.view", "financial.certificates.issue",
    )),
):
    return {
        "permissions": getattr(current_user, "permissions", {}) or {},
        "is_super_admin": bool(getattr(current_user, "is_super_admin", False)),
    }


CANONICAL_SERVICE_TYPES = (
    ("shipping", "شحن", "fixed_per_operation", Decimal("3000")),
    ("delivery", "توصيل", "fixed_per_operation", Decimal("500")),
    ("design", "تصاميم", None, None),
    ("sorting", "فرز", None, None),
    ("other", "أخرى", None, None),
)


@router.get("/service-types")
async def list_service_types(
    ensure_canonical: bool = Query(False),
    _user: UserResponse = Depends(require_any_permission(
        "monthly_entry", "view_companies", "manage_companies_contracts",
        "financial.monthly.view", "financial.monthly.enter", "financial.companies.view",
        "financial.pricing.manage", "financial.member_links.view",
    )),
    db: AsyncSession = Depends(get_db),
):
    if ensure_canonical:
        existing = {
            row.code: row
            for row in (await db.execute(select(ServiceType))).scalars().all()
        }
        changed = False
        for code, name, method, value in CANONICAL_SERVICE_TYPES:
            row = existing.get(code)
            if row is None:
                db.add(ServiceType(
                    code=code,
                    name=name,
                    is_active=True,
                    default_commission_method=method,
                    default_commission_value=value,
                ))
                changed = True
            elif row.name != name or not row.is_active:
                row.name = name
                row.is_active = True
                changed = True
        if changed:
            await db.commit()
    rows = (await db.execute(select(ServiceType).order_by(ServiceType.name))).scalars().all()
    return {"items": [{
        "id": x.id, "name": x.name, "code": x.code, "is_active": x.is_active,
        "default_commission_method": x.default_commission_method,
        "default_commission_value": (
            float(x.default_commission_value)
            if x.default_commission_value is not None else None
        ),
    } for x in rows]}


@router.post("/service-types")
async def create_service_type(
    data: ServiceTypeIn,
    user: UserResponse = Depends(require_any_permission("manage_companies_contracts", "financial.companies.create")),
    db: AsyncSession = Depends(get_db),
):
    if data.default_commission_method and data.default_commission_method not in COMMISSION_METHODS:
        raise HTTPException(400, "طريقة العمولة الافتراضية غير مدعومة")
    actor = await resolve_actor_name(db, user)
    item = ServiceType(**data.model_dump())
    db.add(item)
    await db.flush()
    add_audit(db, action="create", entity_type="service_type", entity_id=item.id, actor=actor, new_values=data.model_dump())
    await db.commit()
    return {"id": item.id, **data.model_dump()}


@router.get("/companies")
async def list_companies(
    service_type_id: Optional[int] = None,
    status: Optional[str] = None,
    user: UserResponse = Depends(require_any_permission(
        "monthly_entry", "view_companies", "manage_companies_contracts", "manage_member_company_accounts",
        "financial.monthly.view", "financial.monthly.enter", "financial.companies.view",
        "financial.pricing.manage", "financial.member_links.view",
    )),
    db: AsyncSession = Depends(get_db),
):
    latest = (
        select(CompanyContract.company_id, func.max(CompanyContract.version).label("version"))
        .group_by(CompanyContract.company_id).subquery()
    )
    stmt = (
        select(FinancialCompany, ServiceType, CompanyContract)
        .join(ServiceType, ServiceType.id == FinancialCompany.service_type_id)
        .outerjoin(latest, latest.c.company_id == FinancialCompany.id)
        .outerjoin(CompanyContract, and_(CompanyContract.company_id == latest.c.company_id, CompanyContract.version == latest.c.version))
        .order_by(ServiceType.name, FinancialCompany.name)
    )
    if service_type_id:
        stmt = stmt.where(FinancialCompany.service_type_id == service_type_id)
    if status:
        stmt = stmt.where(FinancialCompany.status == status)
    rows = (await db.execute(stmt)).all()
    show_contract = bool(
        getattr(user, "is_super_admin", False)
        or (getattr(user, "permissions", {}) or {}).get("manage_companies_contracts")
        or _finance_allowed(user)
    )
    return {"items": [
        {
            "id": c.id, "name": c.name, "service_type_id": c.service_type_id,
            "service_type_name": s.name, "service_type_code": s.code,
            "contact_info": c.contact_info, "status": c.status,
            "contract_start": _iso(c.contract_start), "contract_end": _iso(c.contract_end),
            "notes": c.notes, "owner_name": c.owner_name, "address": c.address,
            "mobile": c.mobile, "cooperation_status": c.cooperation_status,
            "cooperation_started_at": _iso(c.cooperation_started_at),
            "current_contract": None if not ct or not show_contract else {
                "id": ct.id, "version": ct.version, "commission_method": ct.commission_method,
                "commission_value": float(ct.commission_value), "effective_from": _iso(ct.effective_from),
                "effective_to": _iso(ct.effective_to), "attachment_key": ct.attachment_key,
            },
        } for c, s, ct in rows
    ]}


@router.post("/companies")
async def create_company(
    data: CompanyIn,
    user: UserResponse = Depends(require_any_permission("manage_companies_contracts", "financial.companies.create")),
    db: AsyncSession = Depends(get_db),
):
    actor = await resolve_actor_name(db, user)
    service_type = await db.get(ServiceType, data.service_type_id)
    if not service_type:
        raise HTTPException(404, "نوع الخدمة غير موجود")
    payload = data.model_dump()
    if not payload.get("contract_start") and payload.get("cooperation_started_at"):
        payload["contract_start"] = payload["cooperation_started_at"]
    item = FinancialCompany(**payload)
    db.add(item)
    await db.flush()
    effective_from = payload.get("contract_start") or date.today()
    db.add(
        CompanyContract(
            company_id=item.id,
            version=1,
            commission_method=service_type.default_commission_method or "custom",
            commission_value=service_type.default_commission_value or Decimal("0"),
            effective_from=effective_from,
            effective_to=payload.get("contract_end"),
            notes="عقد أساسي ابتدائي — يمكن استكمال بياناته ومرفقاته من تفاصيل الشركة",
            custom_config=json.dumps({"contract_number": None, "signed_at": None}, ensure_ascii=False),
            created_by=actor,
        )
    )
    add_audit(db, action="create", entity_type="company", entity_id=item.id, actor=actor, new_values=payload)
    await db.commit()
    return {"id": item.id, "name": item.name, "service_type_id": item.service_type_id}


@router.put("/companies/{company_id}")
async def update_company(
    company_id: int,
    data: CompanyIn,
    user: UserResponse = Depends(require_any_permission("manage_companies_contracts", "financial.companies.edit")),
    db: AsyncSession = Depends(get_db),
):
    item = await db.get(FinancialCompany, company_id)
    if not item:
        raise HTTPException(404, "الشركة غير موجودة")
    actor = await resolve_actor_name(db, user)
    old = {k: _iso(getattr(item, k)) for k in data.model_dump()}
    for key, value in data.model_dump().items():
        setattr(item, key, value)
    add_audit(db, action="update", entity_type="company", entity_id=item.id, actor=actor, old_values=old, new_values=data.model_dump())
    await db.commit()
    return {"id": item.id}


@router.get("/companies/{company_id}/contracts")
async def list_contracts(
    company_id: int,
    _user: UserResponse = Depends(require_any_permission("view_companies", "manage_companies_contracts", "financial.companies.view", "financial.contracts.manage")),
    db: AsyncSession = Depends(get_db),
):
    rows = (await db.execute(
        select(CompanyContract).where(CompanyContract.company_id == company_id).order_by(CompanyContract.version.desc())
    )).scalars().all()
    return {"items": [
        {
            "id": x.id, "version": x.version, "commission_method": x.commission_method,
            "commission_value": float(x.commission_value), "custom_config": json.loads(x.custom_config) if x.custom_config else None,
            "effective_from": _iso(x.effective_from), "effective_to": _iso(x.effective_to),
            "attachment_key": x.attachment_key, "notes": x.notes, "created_by": x.created_by,
        } for x in rows
    ]}


@router.post("/companies/{company_id}/contracts")
async def create_contract(
    company_id: int,
    data: ContractIn,
    user: UserResponse = Depends(require_any_permission("manage_companies_contracts", "financial.contracts.manage")),
    db: AsyncSession = Depends(get_db),
):
    if data.commission_method not in COMMISSION_METHODS:
        raise HTTPException(400, "طريقة العمولة غير مدعومة")
    if not await db.get(FinancialCompany, company_id):
        raise HTTPException(404, "الشركة غير موجودة")
    version = (await db.execute(
        select(func.coalesce(func.max(CompanyContract.version), 0)).where(CompanyContract.company_id == company_id)
    )).scalar_one() + 1
    actor = await resolve_actor_name(db, user)
    item = CompanyContract(
        company_id=company_id, version=version, created_by=actor,
        custom_config=json.dumps(data.custom_config, ensure_ascii=False) if data.custom_config else None,
        **data.model_dump(exclude={"custom_config"}),
    )
    db.add(item)
    await db.flush()
    add_audit(db, action="create", entity_type="contract", entity_id=item.id, actor=actor, new_values=data.model_dump())
    await db.commit()
    return {"id": item.id, "version": version}


@router.get("/member-accounts")
async def list_member_accounts(
    company_id: Optional[int] = None,
    member_id: Optional[int] = None,
    search: Optional[str] = None,
    _user: UserResponse = Depends(require_any_permission(
        "monthly_entry", "view_companies", "manage_member_company_accounts",
        "financial.monthly.view", "financial.member_links.view",
    )),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(MemberCompanyAccount, Registrations, FinancialCompany, ServiceType)
        .join(Registrations, Registrations.id == MemberCompanyAccount.member_id)
        .join(FinancialCompany, FinancialCompany.id == MemberCompanyAccount.company_id)
        .join(ServiceType, ServiceType.id == FinancialCompany.service_type_id)
        .order_by(Registrations.merchant_name)
    )
    if company_id:
        stmt = stmt.where(MemberCompanyAccount.company_id == company_id)
    if member_id:
        stmt = stmt.where(MemberCompanyAccount.member_id == member_id)
    if search:
        term = f"%{search.strip()}%"
        stmt = stmt.where(or_(
            Registrations.merchant_name.ilike(term), Registrations.membership_number.ilike(term),
            MemberCompanyAccount.registered_name.ilike(term), MemberCompanyAccount.customer_code.ilike(term),
        ))
    rows = (await db.execute(stmt)).all()
    return {"items": [
        {
            "id": a.id, "member_id": m.id, "member_name": m.merchant_name,
            "business_name": m.business_name, "membership_number": m.membership_number, "governorate": m.governorate,
            "membership_status": m.membership_status, "company_id": c.id, "company_name": c.name,
            "service_type_name": s.name, "registered_name": a.registered_name,
            "registered_phone": a.registered_phone, "customer_code": a.customer_code,
            "statement_url": a.statement_url, "customer_portal_url": a.customer_portal_url or a.statement_url,
            "started_at": _iso(a.started_at), "ended_at": _iso(a.ended_at), "status": a.status,
            "notes": a.notes, "is_active": a.is_active,
        } for a, m, c, s in rows
    ]}


@router.get("/members")
async def member_options(
    search: Optional[str] = None,
    _user: UserResponse = Depends(require_any_permission("manage_member_company_accounts", "financial.member_links.create", "financial.member_links.edit")),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(
        Registrations.id, Registrations.merchant_name, Registrations.membership_number,
        Registrations.governorate, Registrations.business_name
    ).where(Registrations.status == "approved").order_by(Registrations.merchant_name).limit(200)
    if search:
        term = f"%{search.strip()}%"
        stmt = stmt.where(or_(Registrations.merchant_name.ilike(term), Registrations.membership_number.ilike(term)))
    rows = (await db.execute(stmt)).all()
    return {"items": [
        {"id": x[0], "member_name": x[1], "membership_number": x[2],
         "governorate": x[3], "business_name": x[4]} for x in rows
    ]}


@router.post("/member-accounts")
async def upsert_member_account(
    data: AccountIn,
    user: UserResponse = Depends(require_any_permission("manage_member_company_accounts", "financial.member_links.create", "financial.member_links.edit")),
    db: AsyncSession = Depends(get_db),
):
    if not await db.get(Registrations, data.member_id):
        raise HTTPException(404, "العضو غير موجود")
    if not await db.get(FinancialCompany, data.company_id):
        raise HTTPException(404, "الشركة غير موجودة")
    result = await db.execute(select(MemberCompanyAccount).where(
        MemberCompanyAccount.member_id == data.member_id,
        MemberCompanyAccount.company_id == data.company_id,
    ))
    item = result.scalar_one_or_none()
    actor = await resolve_actor_name(db, user)
    payload = data.model_dump(exclude={"items"})
    payload["statement_url"] = str(data.statement_url) if data.statement_url else None
    payload["customer_portal_url"] = str(data.customer_portal_url) if data.customer_portal_url else None
    old = None
    if item:
        old = {k: getattr(item, k) for k in payload}
        for key, value in payload.items():
            setattr(item, key, value)
        action = "update"
    else:
        item = MemberCompanyAccount(**payload)
        db.add(item)
        action = "create"
    await db.flush()
    if data.items is not None:
        pricing_ids = [assignment.pricing_item_id for assignment in data.items]
        if len(pricing_ids) != len(set(pricing_ids)):
            raise HTTPException(400, "لا يمكن تكرار فقرة التحاسب نفسها")
        valid_ids = set((await db.execute(
            select(PricingItem.id).where(
                PricingItem.id.in_(pricing_ids),
                PricingItem.company_id == data.company_id,
                PricingItem.is_active.is_(True),
                PricingItem.deleted_at.is_(None),
            )
        )).scalars().all()) if pricing_ids else set()
        if valid_ids != set(pricing_ids):
            raise HTTPException(409, "إحدى فقرات التحاسب غير فعالة أو لا تتبع الشركة")
        existing_items = {
            row.pricing_item_id: row for row in (await db.execute(
                select(MemberAccountItem).where(MemberAccountItem.account_id == item.id)
            )).scalars().all()
        }
        for row in existing_items.values():
            row.is_active = False
        for assignment in data.items:
            row = existing_items.get(assignment.pricing_item_id) or MemberAccountItem(
                account_id=item.id, pricing_item_id=assignment.pricing_item_id
            )
            for key, value in assignment.model_dump().items():
                setattr(row, key, value)
            db.add(row)
    add_audit(db, action=action, entity_type="member_company_account", entity_id=item.id, actor=actor, old_values=old, new_values=payload)
    await db.commit()
    return {"id": item.id, "saved_items": len(data.items) if data.items is not None else None}


@router.get("/monthly-entry")
async def monthly_sheet(
    company_id: int,
    accounting_year: int,
    accounting_month: int,
    user: UserResponse = Depends(require_any_permission("monthly_entry", *FINANCIAL_VIEW_PERMS)),
    db: AsyncSession = Depends(get_db),
):
    period = (await db.execute(select(AccountingPeriod).where(
        AccountingPeriod.company_id == company_id,
        AccountingPeriod.accounting_year == accounting_year,
        AccountingPeriod.accounting_month == accounting_month,
    ))).scalar_one_or_none()
    stmt = (
        select(MemberCompanyAccount, Registrations, MonthlyActivity)
        .join(Registrations, Registrations.id == MemberCompanyAccount.member_id)
        .outerjoin(
            MonthlyActivity,
            and_(
                MonthlyActivity.member_id == MemberCompanyAccount.member_id,
                MonthlyActivity.period_id == (period.id if period else -1),
            ),
        )
        .where(MemberCompanyAccount.company_id == company_id, MemberCompanyAccount.is_active.is_(True))
        .order_by(Registrations.membership_number, Registrations.merchant_name)
    )
    show_finance = _finance_allowed(user)
    items = []
    for account, member, activity in (await db.execute(stmt)).all():
        row = {
            "member_id": member.id, "member_name": member.merchant_name,
            "membership_number": member.membership_number, "governorate": member.governorate,
            "registered_name": account.registered_name, "registered_phone": account.registered_phone,
            "customer_code": account.customer_code, "statement_url": account.statement_url,
            "operation_count": activity.operation_count if activity else 0,
            "gross_business_value": float(activity.gross_business_value) if activity else 0,
        }
        if show_finance and activity:
            row.update({
                "commission_method": activity.commission_method_snapshot,
                "commission_value": float(activity.commission_value_snapshot),
                "revenue_amount": float(activity.revenue_amount),
            })
        items.append(row)
    return {
        "period_id": period.id if period else None,
        "status": period.status if period else "not_started",
        "items": items,
    }


@router.put("/monthly-entry/bulk")
async def save_monthly_bulk(
    data: MonthlyBulkIn,
    user: UserResponse = Depends(require_permission("monthly_entry")),
    db: AsyncSession = Depends(get_db),
):
    company_row = (await db.execute(
        select(FinancialCompany, ServiceType)
        .join(ServiceType, ServiceType.id == FinancialCompany.service_type_id)
        .where(FinancialCompany.id == data.company_id)
    )).one_or_none()
    if not company_row:
        raise HTTPException(404, "الشركة غير موجودة")
    company, service_type = company_row
    period_date = date(data.accounting_year, data.accounting_month, 1)
    contract = await _active_contract(db, data.company_id, period_date)
    period = (await db.execute(select(AccountingPeriod).where(
        AccountingPeriod.company_id == data.company_id,
        AccountingPeriod.accounting_year == data.accounting_year,
        AccountingPeriod.accounting_month == data.accounting_month,
    ).with_for_update())).scalar_one_or_none()
    if period and period.status == "closed" and not (
        getattr(user, "is_super_admin", False) or (getattr(user, "permissions", {}) or {}).get("manage_periods")
    ):
        raise HTTPException(409, "الشهر مغلق ولا يمكن تعديله")
    if not period:
        period = AccountingPeriod(
            company_id=data.company_id, accounting_year=data.accounting_year,
            accounting_month=data.accounting_month, status="in_progress",
        )
        db.add(period)
        await db.flush()
    member_ids = {row.member_id for row in data.rows}
    valid_ids = set((await db.execute(
        select(MemberCompanyAccount.member_id).where(
            MemberCompanyAccount.company_id == data.company_id,
            MemberCompanyAccount.member_id.in_(member_ids),
            MemberCompanyAccount.is_active.is_(True),
        )
    )).scalars().all())
    if member_ids != valid_ids:
        raise HTTPException(400, "تتضمن البيانات عضوًا غير مرتبط بالشركة")
    existing = {
        x.member_id: x for x in (await db.execute(
            select(MonthlyActivity).where(
                MonthlyActivity.period_id == period.id,
                MonthlyActivity.member_id.in_(member_ids),
            )
        )).scalars().all()
    }
    actor = await resolve_actor_name(db, user)
    monthly_fixed_allocations: dict[int, Decimal] = {}
    if contract.commission_method == "monthly_fixed" and data.rows:
        monthly_total = _decimal(contract.commission_value)
        total_operations = sum(row.operation_count for row in data.rows)
        allocated = Decimal("0")
        for index, row in enumerate(data.rows):
            if index == len(data.rows) - 1:
                share = monthly_total - allocated
            elif total_operations:
                share = (monthly_total * Decimal(row.operation_count) / Decimal(total_operations)).quantize(Decimal("0.001"))
            else:
                share = monthly_total if index == 0 else Decimal("0")
            monthly_fixed_allocations[row.member_id] = share
            allocated += share
    for row in data.rows:
        revenue = (
            monthly_fixed_allocations[row.member_id]
            if contract.commission_method == "monthly_fixed"
            else calculate_revenue(
                contract.commission_method, contract.commission_value,
                row.operation_count, row.gross_business_value,
            )
        )
        item = existing.get(row.member_id)
        old = None
        if item:
            old = {"operation_count": item.operation_count, "revenue_amount": str(item.revenue_amount)}
            item.operation_count = row.operation_count
            item.gross_business_value = row.gross_business_value
            item.commission_method_snapshot = contract.commission_method
            item.commission_value_snapshot = contract.commission_value
            item.revenue_amount = revenue
            item.updated_by = actor
        else:
            item = MonthlyActivity(
                period_id=period.id, member_id=row.member_id, company_id=company.id,
                service_type_id=service_type.id, operation_count=row.operation_count,
                gross_business_value=row.gross_business_value,
                commission_method_snapshot=contract.commission_method,
                commission_value_snapshot=contract.commission_value,
                revenue_amount=revenue, entered_by=actor, updated_by=actor,
            )
            db.add(item)
        add_audit(
            db, action="monthly_upsert", entity_type="monthly_activity",
            entity_id=item.id, actor=actor, old_values=old,
            new_values={"member_id": row.member_id, "operation_count": row.operation_count, "revenue_amount": str(revenue)},
        )
    period.status = "complete" if data.mark_complete else "in_progress"
    await db.commit()
    return {"period_id": period.id, "status": period.status, "saved": len(data.rows)}


@router.patch("/periods/{period_id}/status")
async def change_period_status(
    period_id: int,
    data: PeriodStatusIn,
    user: UserResponse = Depends(require_permission("manage_periods")),
    db: AsyncSession = Depends(get_db),
):
    period = await db.get(AccountingPeriod, period_id)
    if not period:
        raise HTTPException(404, "الشهر غير موجود")
    actor = await resolve_actor_name(db, user)
    old = period.status
    period.status = data.status
    if data.status == "closed":
        period.approved_by, period.approved_at = actor, datetime.now()
    else:
        period.approved_by, period.approved_at = None, None
    add_audit(db, action="period_status", entity_type="accounting_period", entity_id=period.id, actor=actor, old_values={"status": old}, new_values={"status": data.status})
    await db.commit()
    return {"id": period.id, "status": period.status}


@router.get("/expenses")
async def list_expenses(
    accounting_year: Optional[int] = None,
    accounting_month: Optional[int] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    include_deleted: bool = False,
    _user: UserResponse = Depends(require_any_permission("view_expenses", "financial.expenses.view")),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(FinancialExpense).order_by(FinancialExpense.expense_date.desc())
    if accounting_year:
        stmt = stmt.where(FinancialExpense.accounting_year == accounting_year)
    if accounting_month:
        stmt = stmt.where(FinancialExpense.accounting_month == accounting_month)
    if date_from:
        stmt = stmt.where(FinancialExpense.expense_date >= date_from)
    if date_to:
        stmt = stmt.where(FinancialExpense.expense_date <= date_to)
    if not include_deleted:
        stmt = stmt.where(FinancialExpense.deleted_at.is_(None))
    rows = (await db.execute(stmt)).scalars().all()
    return {"items": [
        {
            "id": x.id, "expense_date": _iso(x.expense_date), "accounting_year": x.accounting_year,
            "accounting_month": x.accounting_month, "category": x.category,
            "description": x.description, "amount": float(x.amount), "notes": x.notes,
            "receipt_key": x.receipt_key, "created_by": x.created_by,
            "deleted": bool(x.deleted_at), "deleted_at": _iso(x.deleted_at),
        } for x in rows
    ]}


@router.post("/expenses")
async def create_expense(
    data: ExpenseIn,
    user: UserResponse = Depends(require_any_permission("enter_expenses", "financial.expenses.create")),
    db: AsyncSession = Depends(get_db),
):
    actor = await resolve_actor_name(db, user)
    item = FinancialExpense(**data.model_dump(), created_by=actor, updated_by=actor)
    db.add(item)
    await db.flush()
    add_audit(db, action="create", entity_type="expense", entity_id=item.id, actor=actor, new_values=data.model_dump())
    await db.commit()
    return {"id": item.id}


@router.put("/expenses/{expense_id}")
async def update_expense(
    expense_id: int,
    data: ExpenseIn,
    user: UserResponse = Depends(require_any_permission("enter_expenses", "financial.expenses.edit")),
    db: AsyncSession = Depends(get_db),
):
    item = await db.get(FinancialExpense, expense_id)
    if not item:
        raise HTTPException(404, "المصروف غير موجود")
    actor = await resolve_actor_name(db, user)
    old = {k: _iso(getattr(item, k)) for k in data.model_dump()}
    for key, value in data.model_dump().items():
        setattr(item, key, value)
    item.updated_by = actor
    add_audit(db, action="update", entity_type="expense", entity_id=item.id, actor=actor, old_values=old, new_values=data.model_dump())
    await db.commit()
    return {"id": item.id}


@router.get("/dashboard")
async def financial_dashboard(
    accounting_year: int,
    accounting_month: int,
    _user: UserResponse = Depends(require_any_permission("view_revenue", "view_profits")),
    db: AsyncSession = Depends(get_db),
):
    totals = (await db.execute(
        select(
            func.coalesce(func.sum(MonthlyActivity.revenue_amount), 0),
            func.coalesce(func.sum(MonthlyActivity.operation_count), 0),
        ).join(AccountingPeriod, AccountingPeriod.id == MonthlyActivity.period_id).where(
            AccountingPeriod.accounting_year == accounting_year,
            AccountingPeriod.accounting_month == accounting_month,
        )
    )).one()
    expense_total = (await db.execute(select(func.coalesce(func.sum(FinancialExpense.amount), 0)).where(
        FinancialExpense.accounting_year == accounting_year,
        FinancialExpense.accounting_month == accounting_month,
    ))).scalar_one()
    by_service = (await db.execute(
        select(ServiceType.name, func.sum(MonthlyActivity.revenue_amount), func.sum(MonthlyActivity.operation_count))
        .join(MonthlyActivity, MonthlyActivity.service_type_id == ServiceType.id)
        .join(AccountingPeriod, AccountingPeriod.id == MonthlyActivity.period_id)
        .where(AccountingPeriod.accounting_year == accounting_year, AccountingPeriod.accounting_month == accounting_month)
        .group_by(ServiceType.id, ServiceType.name)
    )).all()
    top_companies = (await db.execute(
        select(FinancialCompany.name, func.sum(MonthlyActivity.operation_count), func.sum(MonthlyActivity.revenue_amount))
        .join(MonthlyActivity, MonthlyActivity.company_id == FinancialCompany.id)
        .join(AccountingPeriod, AccountingPeriod.id == MonthlyActivity.period_id)
        .where(AccountingPeriod.accounting_year == accounting_year, AccountingPeriod.accounting_month == accounting_month)
        .group_by(FinancialCompany.id, FinancialCompany.name)
        .order_by(func.sum(MonthlyActivity.operation_count).desc()).limit(5)
    )).all()
    top_members = (await db.execute(
        select(
            Registrations.id, Registrations.merchant_name,
            Registrations.membership_number,
            func.sum(MonthlyActivity.operation_count),
            func.sum(MonthlyActivity.revenue_amount),
        )
        .join(MonthlyActivity, MonthlyActivity.member_id == Registrations.id)
        .join(AccountingPeriod, AccountingPeriod.id == MonthlyActivity.period_id)
        .where(AccountingPeriod.accounting_year == accounting_year, AccountingPeriod.accounting_month == accounting_month)
        .group_by(Registrations.id, Registrations.merchant_name, Registrations.membership_number)
        .order_by(func.sum(MonthlyActivity.operation_count).desc()).limit(5)
    )).all()
    revenue = _decimal(totals[0])
    return {
        "total_revenue": float(revenue), "total_expenses": float(expense_total),
        "net_profit": float(revenue - _decimal(expense_total)), "total_operations": int(totals[1]),
        "by_service": [{"name": x[0], "revenue": float(x[1] or 0), "operations": int(x[2] or 0)} for x in by_service],
        "top_companies": [{"name": x[0], "operations": int(x[1] or 0), "revenue": float(x[2] or 0)} for x in top_companies],
        "top_members": [
            {
                "member_id": x[0], "name": x[1], "membership_number": x[2],
                "operations": int(x[3] or 0), "revenue": float(x[4] or 0),
            } for x in top_members
        ],
    }


@router.get("/reports/members")
async def member_report(
    accounting_year: Optional[int] = None,
    accounting_month: Optional[int] = None,
    company_id: Optional[int] = None,
    service_type_id: Optional[int] = None,
    member_id: Optional[int] = None,
    governorate: Optional[str] = None,
    _user: UserResponse = Depends(require_permission("view_financial_reports")),
    db: AsyncSession = Depends(get_db),
):
    return {"items": await _report_rows(
        db, year=accounting_year, month=accounting_month, company_id=company_id,
        service_type_id=service_type_id, member_id=member_id, governorate=governorate,
    )}


@router.get("/reports/members.xlsx")
async def member_report_xlsx(
    accounting_year: Optional[int] = None,
    accounting_month: Optional[int] = None,
    company_id: Optional[int] = None,
    service_type_id: Optional[int] = None,
    member_id: Optional[int] = None,
    governorate: Optional[str] = None,
    _user: UserResponse = Depends(require_permission("export_excel")),
    db: AsyncSession = Depends(get_db),
):
    rows = await _report_rows(
        db, year=accounting_year, month=accounting_month, company_id=company_id,
        service_type_id=service_type_id, member_id=member_id, governorate=governorate,
    )
    payload = build_financial_xlsx(
        rows, "تقرير الإدارة المالية والنشاطات",
        f"السنة: {accounting_year or 'الكل'} | الشهر: {accounting_month or 'الكل'}",
    )
    return StreamingResponse(
        io.BytesIO(payload),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="financial-report.xlsx"'},
    )


@router.get("/statements/{member_id}")
async def member_statement(
    member_id: int,
    accounting_year: Optional[int] = None,
    accounting_month: Optional[int] = None,
    _user: UserResponse = Depends(require_permission("view_statements")),
    db: AsyncSession = Depends(get_db),
):
    rows = (await db.execute(
        select(
            FinancialCompany.name, ServiceType.name, AccountingPeriod.accounting_year,
            AccountingPeriod.accounting_month, MonthlyActivity.operation_count,
            MonthlyActivity.revenue_amount,
        )
        .join(FinancialCompany, FinancialCompany.id == MonthlyActivity.company_id)
        .join(ServiceType, ServiceType.id == MonthlyActivity.service_type_id)
        .join(AccountingPeriod, AccountingPeriod.id == MonthlyActivity.period_id)
        .where(MonthlyActivity.member_id == member_id)
        .order_by(AccountingPeriod.accounting_year.desc(), AccountingPeriod.accounting_month.desc())
    )).all()
    if accounting_year:
        rows = [x for x in rows if x[2] == accounting_year]
    if accounting_month:
        rows = [x for x in rows if x[3] == accounting_month]
    return {
        "member_id": member_id,
        "items": [
            {
                "company_name": x[0], "service_type_name": x[1],
                "accounting_year": x[2], "accounting_month": x[3],
                "operations": int(x[4] or 0), "revenue": float(x[5] or 0),
            } for x in rows
        ],
    }
@router.get("/ranking")
async def ranking(
    accounting_year: int,
    accounting_month: int,
    basis: Literal["operations", "revenue"] = "operations",
    _user: UserResponse = Depends(require_any_permission("view_financial_reports", "issue_distinguished_certificate")),
    db: AsyncSession = Depends(get_db),
):
    metric = func.sum(MonthlyActivity.operation_count) if basis == "operations" else func.sum(MonthlyActivity.revenue_amount)
    rows = (await db.execute(
        select(
            Registrations.id, Registrations.merchant_name, Registrations.membership_number,
            func.sum(MonthlyActivity.operation_count), func.sum(MonthlyActivity.revenue_amount),
        )
        .join(MonthlyActivity, MonthlyActivity.member_id == Registrations.id)
        .join(AccountingPeriod, AccountingPeriod.id == MonthlyActivity.period_id)
        .where(AccountingPeriod.accounting_year == accounting_year, AccountingPeriod.accounting_month == accounting_month)
        .group_by(Registrations.id, Registrations.merchant_name, Registrations.membership_number)
        .order_by(metric.desc()).limit(50)
    )).all()
    winner = (await db.execute(select(DistinguishedMember).where(
        DistinguishedMember.accounting_year == accounting_year,
        DistinguishedMember.accounting_month == accounting_month,
    ))).scalar_one_or_none()
    return {
        "items": [{"member_id": x[0], "member_name": x[1], "membership_number": x[2], "operations": int(x[3] or 0), "revenue": float(x[4] or 0)} for x in rows],
        "winner": None if not winner else {"id": winner.id, "member_id": winner.member_id, "ranking_basis": winner.ranking_basis},
    }


@router.post("/distinguished-members")
async def select_winner(
    data: WinnerIn,
    user: UserResponse = Depends(require_permission("issue_distinguished_certificate")),
    db: AsyncSession = Depends(get_db),
):
    if not await db.get(Registrations, data.member_id):
        raise HTTPException(404, "العضو غير موجود")
    existing = (await db.execute(select(DistinguishedMember).where(
        DistinguishedMember.accounting_year == data.accounting_year,
        DistinguishedMember.accounting_month == data.accounting_month,
    ))).scalar_one_or_none()
    actor = await resolve_actor_name(db, user)
    if existing:
        old = {"member_id": existing.member_id, "ranking_basis": existing.ranking_basis}
        existing.member_id, existing.ranking_basis = data.member_id, data.ranking_basis
        existing.confirmed_by, existing.confirmed_at = actor, datetime.now()
        item = existing
    else:
        old = None
        item = DistinguishedMember(**data.model_dump(), confirmed_by=actor)
        db.add(item)
        await db.flush()
    add_audit(db, action="confirm_winner", entity_type="distinguished_member", entity_id=item.id, actor=actor, old_values=old, new_values=data.model_dump())
    await db.commit()
    return {"id": item.id}


@router.post("/certificates")
async def issue_certificate(
    data: CertificateIn,
    user: UserResponse = Depends(require_permission("issue_distinguished_certificate")),
    db: AsyncSession = Depends(get_db),
):
    winner = await db.get(DistinguishedMember, data.winner_id)
    if not winner:
        raise HTTPException(404, "الفائز غير موجود")
    actor = await resolve_actor_name(db, user)
    number = f"MFEC-CERT-{winner.accounting_year}{winner.accounting_month:02d}-{winner.member_id}-{uuid.uuid4().hex[:8].upper()}"
    item = MemberCertificate(
        winner_id=winner.id, member_id=winner.member_id, certificate_number=number,
        file_key=data.file_key, issued_by=actor,
    )
    db.add(item)
    await db.flush()
    add_audit(db, action="issue_certificate", entity_type="certificate", entity_id=item.id, actor=actor, new_values={"certificate_number": number})
    await db.commit()
    member = await db.get(Registrations, winner.member_id)
    return {
        "id": item.id, "certificate_number": number, "member_name": member.merchant_name,
        "membership_number": member.membership_number, "accounting_year": winner.accounting_year,
        "accounting_month": winner.accounting_month, "issued_at": _iso(item.issued_at),
    }


@router.get("/certificates")
async def certificate_history(
    accounting_year: Optional[int] = None,
    accounting_month: Optional[int] = None,
    _user: UserResponse = Depends(require_any_permission(
        "view_financial_reports", "issue_distinguished_certificate"
    )),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(MemberCertificate, DistinguishedMember, Registrations)
        .join(DistinguishedMember, DistinguishedMember.id == MemberCertificate.winner_id)
        .join(Registrations, Registrations.id == MemberCertificate.member_id)
        .order_by(MemberCertificate.issued_at.desc())
    )
    if accounting_year:
        stmt = stmt.where(DistinguishedMember.accounting_year == accounting_year)
    if accounting_month:
        stmt = stmt.where(DistinguishedMember.accounting_month == accounting_month)
    rows = (await db.execute(stmt)).all()
    return {"items": [
        {
            "id": cert.id, "certificate_number": cert.certificate_number,
            "member_id": member.id, "member_name": member.merchant_name,
            "membership_number": member.membership_number,
            "accounting_year": winner.accounting_year,
            "accounting_month": winner.accounting_month,
            "issued_by": cert.issued_by, "issued_at": _iso(cert.issued_at),
            "file_key": cert.file_key,
        }
        for cert, winner, member in rows
    ]}


@router.get("/audit")
async def financial_audit(
    limit: int = Query(100, ge=1, le=500),
    _user: UserResponse = Depends(require_permission("view_audit_log")),
    db: AsyncSession = Depends(get_db),
):
    rows = (await db.execute(select(FinancialAuditLog).order_by(FinancialAuditLog.created_at.desc()).limit(limit))).scalars().all()
    return {"items": [
        {
            "id": x.id, "action": x.action, "entity_type": x.entity_type, "entity_id": x.entity_id,
            "actor": x.actor, "old_values": json.loads(x.old_values) if x.old_values else None,
            "new_values": json.loads(x.new_values) if x.new_values else None, "created_at": _iso(x.created_at),
        } for x in rows
    ]}


@router.post("/documents/{kind}")
async def upload_private_document(
    kind: Literal["contracts", "price-lists", "annexes", "statements", "settlements", "receipts", "certificates"],
    file: UploadFile = File(...),
    user: UserResponse = Depends(require_any_permission(
        "manage_companies_contracts", "enter_expenses", "issue_distinguished_certificate",
        "financial.contracts.manage", "financial.annexes.manage", "financial.monthly.enter",
        "financial.monthly.edit", "financial.settlements.create", "financial.revenues.create",
        "financial.revenues.edit", "financial.expenses.create", "financial.expenses.edit",
    )),
):
    allowed = {
        "application/pdf", "image/jpeg", "image/png", "image/webp",
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.ms-excel",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }
    if file.content_type not in allowed:
        raise HTTPException(400, "صيغة المرفق غير مدعومة")
    content = await file.read(10 * 1024 * 1024 + 1)
    if not content or len(content) > 10 * 1024 * 1024:
        raise HTTPException(400, "حجم الملف يجب ألا يتجاوز 10MB")
    suffix = {
        "application/pdf": ".pdf", "image/jpeg": ".jpg",
        "image/png": ".png", "image/webp": ".webp",
        "application/msword": ".doc",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
        "application/vnd.ms-excel": ".xls",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    }[file.content_type]
    key = f"financial/{kind}/{datetime.utcnow():%Y/%m}/{uuid.uuid4().hex}{suffix}"
    await supabase_storage.upload_private_financial_bytes(
        key, content, content_type=file.content_type
    )
    return {"object_key": key}


@router.get("/documents")
async def download_private_document(
    object_key: str,
    _user: UserResponse = Depends(require_any_permission(
        "view_companies", "manage_companies_contracts", "view_expenses",
        "enter_expenses", "print_pdf", "issue_distinguished_certificate",
        "financial.companies.view", "financial.contracts.manage", "financial.member_links.view",
        "financial.annexes.manage", "financial.monthly.view", "financial.settlements.view",
        "financial.revenues.view", "financial.expenses.view", "financial.reports.view",
    )),
):
    if not object_key.startswith("financial/") or ".." in object_key:
        raise HTTPException(400, "مسار الملف غير صالح")
    content, content_type = await supabase_storage.download_private_financial_bytes(
        object_key
    )
    return StreamingResponse(io.BytesIO(content), media_type=content_type)
