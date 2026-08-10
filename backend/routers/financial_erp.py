"""Professional financial ERP endpoints layered additively over the legacy API."""
from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from dependencies.permissions import require_any_permission, require_permission
from models.financial import (
    CompanyAttachment, FinancialCompany, FinancialExpense, MemberAccountItem, MemberAnnex, MemberCompanyAccount,
    MonthlyEntryLine, MonthlyStatement, PricingItem, PricingItemVersion,
    ReceiptAllocation, RevenueReceipt, ServiceType, SettlementBatch, SettlementLine,
    SettlementReversal, StatementAttachment,
)
from models.registrations import Registrations
from schemas.auth import UserResponse
from services.actor import resolve_actor_name
from services.financial import add_audit, build_erp_xlsx, build_financial_xlsx
from services.financial_erp import (
    calculate_line, money, resolve_account_item_pricing, validate_and_add_allocation,
)

router = APIRouter(prefix="/api/v1/admin/financial", tags=["financial-erp"])


def _is_finance_user(user: UserResponse) -> bool:
    p = getattr(user, "permissions", {}) or {}
    return bool(getattr(user, "is_super_admin", False) or any(p.get(x) for x in (
        "financial.dashboard.view", "financial.reports.view", "financial.revenues.view",
        "financial.settlements.view", "view_revenue", "view_profits", "view_financial_reports",
    )))


class PricingItemIn(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    unit: str = Field(min_length=1, max_length=80)
    company_unit_price: Decimal = Field(ge=0)
    mfec_share_type: Literal["fixed", "percentage"]
    mfec_share_value: Decimal = Field(ge=0)
    effective_from: date
    effective_to: date | None = None
    notes: str | None = None


class AccountItemIn(BaseModel):
    pricing_item_id: int
    unit_price_override: Decimal | None = Field(default=None, ge=0)
    mfec_share_type_override: Literal["fixed", "percentage"] | None = None
    mfec_share_value_override: Decimal | None = Field(default=None, ge=0)
    started_at: date | None = None
    ended_at: date | None = None
    is_active: bool = True
    notes: str | None = None


class StatementLineIn(BaseModel):
    account_item_id: int
    quantity: Decimal = Field(ge=0)
    excluded: bool = False
    exclusion_reason: str | None = None


class StatementBulkIn(BaseModel):
    company_id: int
    accounting_year: int = Field(ge=2000, le=2200)
    accounting_month: int = Field(ge=1, le=12)
    received_at: date | None = None
    notes: str | None = None
    lines: list[StatementLineIn]


class ReopenIn(BaseModel):
    reason: str = Field(min_length=3)


class SettlementIn(BaseModel):
    company_id: int
    entry_line_ids: list[int] = Field(min_length=1)
    settled_at: date
    reference_number: str | None = None
    notes: str | None = None
    attachment_key: str | None = None


class ReverseIn(BaseModel):
    reason: str = Field(min_length=3)


class ReceiptIn(BaseModel):
    receipt_number: str = Field(min_length=1, max_length=80)
    company_id: int
    received_at: date
    amount: Decimal = Field(gt=0)
    receipt_method: str = Field(min_length=1, max_length=80)
    category: str | None = None
    description: str = Field(min_length=1, max_length=500)
    period_start: date | None = None
    period_end: date | None = None
    notes: str | None = None
    attachment_key: str | None = None


class ReceiptUpdateIn(ReceiptIn):
    pass


class AllocationIn(BaseModel):
    statement_id: int | None = None
    settlement_batch_id: int | None = None
    amount: Decimal = Field(gt=0)


class DocumentMetaIn(BaseModel):
    object_key: str = Field(min_length=5, max_length=500)
    original_filename: str = Field(min_length=1, max_length=255)
    mime_type: str = Field(min_length=3, max_length=120)
    size_bytes: int = Field(gt=0, le=10 * 1024 * 1024)
    document_type: str = Field(default="contract", max_length=40)
    contract_id: int | None = None
    replaced_id: int | None = None
    signed_at: date | None = None


@router.get("/pricing-items")
async def list_pricing_items(
    company_id: int,
    _user: UserResponse = Depends(require_any_permission(
        "financial.companies.view", "financial.pricing.manage", "financial.member_links.view", "financial.monthly.view"
    )),
    db: AsyncSession = Depends(get_db),
):
    latest = select(
        PricingItemVersion.pricing_item_id, func.max(PricingItemVersion.version).label("version")
    ).group_by(PricingItemVersion.pricing_item_id).subquery()
    rows = (await db.execute(
        select(PricingItem, PricingItemVersion)
        .outerjoin(latest, latest.c.pricing_item_id == PricingItem.id)
        .outerjoin(PricingItemVersion, and_(
            PricingItemVersion.pricing_item_id == latest.c.pricing_item_id,
            PricingItemVersion.version == latest.c.version,
        ))
        .where(PricingItem.company_id == company_id, PricingItem.deleted_at.is_(None))
        .order_by(PricingItem.name)
    )).all()
    return {"items": [{
        "id": item.id, "company_id": item.company_id, "name": item.name, "unit": item.unit,
        "is_active": item.is_active, "notes": item.notes,
        "current_version": None if not version else {
            "id": version.id, "version": version.version,
            "company_unit_price": float(version.company_unit_price),
            "mfec_share_type": version.mfec_share_type,
            "mfec_share_value": float(version.mfec_share_value),
            "effective_from": version.effective_from.isoformat(),
            "effective_to": version.effective_to.isoformat() if version.effective_to else None,
        },
    } for item, version in rows]}


@router.post("/companies/{company_id}/pricing-items")
async def create_pricing_item(
    company_id: int, data: PricingItemIn,
    user: UserResponse = Depends(require_permission("financial.pricing.manage")),
    db: AsyncSession = Depends(get_db),
):
    if not await db.get(FinancialCompany, company_id):
        raise HTTPException(404, "الشركة غير موجودة")
    actor = await resolve_actor_name(db, user)
    item = PricingItem(company_id=company_id, name=data.name, unit=data.unit, notes=data.notes)
    db.add(item); await db.flush()
    version = PricingItemVersion(
        pricing_item_id=item.id, version=1, company_unit_price=money(data.company_unit_price),
        mfec_share_type=data.mfec_share_type, mfec_share_value=money(data.mfec_share_value),
        effective_from=data.effective_from, effective_to=data.effective_to,
        notes=data.notes, created_by=actor,
    )
    db.add(version)
    add_audit(db, action="pricing_item.create", entity_type="pricing_item", entity_id=item.id, actor=actor, new_values=data.model_dump())
    await db.commit()
    return {"id": item.id, "version_id": version.id}


@router.get("/companies/{company_id}/attachments")
async def company_attachments(
    company_id:int,
    _user:UserResponse=Depends(require_any_permission("financial.companies.view","financial.contracts.manage")),
    db:AsyncSession=Depends(get_db),
):
    rows=(await db.execute(select(CompanyAttachment).where(
        CompanyAttachment.company_id==company_id,CompanyAttachment.deleted_at.is_(None)
    ).order_by(CompanyAttachment.uploaded_at.desc()))).scalars().all()
    return {"items":[{"id":x.id,"document_type":x.document_type,"object_key":x.object_key,
        "original_filename":x.original_filename,"mime_type":x.mime_type,"size_bytes":x.size_bytes,
        "uploaded_at":x.uploaded_at.isoformat() if x.uploaded_at else None} for x in rows]}


@router.post("/companies/{company_id}/attachments")
async def add_company_attachment(
    company_id:int,data:DocumentMetaIn,
    user:UserResponse=Depends(require_permission("financial.contracts.manage")),db:AsyncSession=Depends(get_db),
):
    if not await db.get(FinancialCompany,company_id): raise HTTPException(404,"الشركة غير موجودة")
    if not data.object_key.startswith("financial/"): raise HTTPException(400,"مسار المستند غير صالح")
    actor=await resolve_actor_name(db,user)
    if data.replaced_id:
        replaced=await db.get(CompanyAttachment,data.replaced_id)
        if not replaced or replaced.company_id!=company_id:raise HTTPException(409,"المرفق المستبدل لا يتبع الشركة")
        replaced.deleted_at=datetime.now();replaced.deleted_by=actor
    row=CompanyAttachment(company_id=company_id,contract_id=data.contract_id,document_type=data.document_type,
        object_key=data.object_key,original_filename=data.original_filename,mime_type=data.mime_type,
        size_bytes=data.size_bytes,uploaded_by=actor,replaced_attachment_id=data.replaced_id)
    db.add(row);await db.flush()
    add_audit(db,action="company_attachment.create",entity_type="company_attachment",entity_id=row.id,actor=actor,new_values=data.model_dump())
    await db.commit();return {"id":row.id}


@router.delete("/companies/{company_id}/attachments/{attachment_id}")
async def delete_company_attachment(
    company_id:int,attachment_id:int,user:UserResponse=Depends(require_permission("financial.contracts.manage")),
    db:AsyncSession=Depends(get_db),
):
    row=await db.get(CompanyAttachment,attachment_id)
    if not row or row.company_id!=company_id: raise HTTPException(404,"المرفق غير موجود")
    actor=await resolve_actor_name(db,user);row.deleted_at=datetime.now();row.deleted_by=actor
    add_audit(db,action="company_attachment.delete",entity_type="company_attachment",entity_id=row.id,actor=actor)
    await db.commit();return {"id":row.id,"deleted":True}


@router.delete("/member-accounts/{account_id}/annexes/{annex_id}")
async def delete_annex(
    account_id:int,annex_id:int,user:UserResponse=Depends(require_permission("financial.annexes.manage")),
    db:AsyncSession=Depends(get_db),
):
    row=await db.get(MemberAnnex,annex_id)
    if not row or row.account_id!=account_id:raise HTTPException(404,"الملحق غير موجود")
    actor=await resolve_actor_name(db,user);row.deleted_at=datetime.now();row.deleted_by=actor
    add_audit(db,action="annex.delete",entity_type="member_annex",entity_id=row.id,actor=actor)
    await db.commit();return {"id":row.id,"deleted":True}


@router.post("/pricing-items/{item_id}/versions")
async def create_pricing_version(
    item_id: int, data: PricingItemIn,
    user: UserResponse = Depends(require_permission("financial.pricing.manage")),
    db: AsyncSession = Depends(get_db),
):
    item = await db.get(PricingItem, item_id)
    if not item: raise HTTPException(404, "البند غير موجود")
    version_no = (await db.execute(
        select(func.coalesce(func.max(PricingItemVersion.version), 0)).where(PricingItemVersion.pricing_item_id == item_id)
    )).scalar_one() + 1
    actor = await resolve_actor_name(db, user)
    version = PricingItemVersion(
        pricing_item_id=item_id, version=version_no,
        company_unit_price=money(data.company_unit_price), mfec_share_type=data.mfec_share_type,
        mfec_share_value=money(data.mfec_share_value), effective_from=data.effective_from,
        effective_to=data.effective_to, notes=data.notes, created_by=actor,
    )
    db.add(version)
    add_audit(db, action="pricing.version", entity_type="pricing_item", entity_id=item_id, actor=actor, new_values=data.model_dump())
    await db.commit()
    return {"id": version.id, "version": version_no}


@router.get("/pricing-items/{item_id}/versions")
async def list_pricing_versions(
    item_id:int,_user:UserResponse=Depends(require_any_permission("financial.companies.view","financial.pricing.manage")),
    db:AsyncSession=Depends(get_db),
):
    rows=(await db.execute(select(PricingItemVersion).where(
        PricingItemVersion.pricing_item_id==item_id).order_by(PricingItemVersion.version.desc()))).scalars().all()
    return {"items":[{"id":x.id,"version":x.version,"company_unit_price":float(x.company_unit_price),
        "mfec_share_type":x.mfec_share_type,"mfec_share_value":float(x.mfec_share_value),
        "effective_from":x.effective_from.isoformat(),"effective_to":x.effective_to.isoformat() if x.effective_to else None,
        "notes":x.notes,"created_by":x.created_by} for x in rows]}


@router.get("/member-accounts/{account_id}/items")
async def list_account_items(
    account_id: int,
    _user: UserResponse = Depends(require_any_permission("financial.member_links.view", "financial.monthly.view")),
    db: AsyncSession = Depends(get_db),
):
    account=await db.get(MemberCompanyAccount,account_id)
    if not account:raise HTTPException(404,"ارتباط العضو غير موجود")
    latest=select(PricingItemVersion.pricing_item_id,func.max(PricingItemVersion.version).label("version")).group_by(
        PricingItemVersion.pricing_item_id).subquery()
    rows = (await db.execute(
        select(MemberAccountItem, PricingItem, PricingItemVersion)
        .join(PricingItem, PricingItem.id == MemberAccountItem.pricing_item_id)
        .outerjoin(latest,latest.c.pricing_item_id==PricingItem.id)
        .outerjoin(PricingItemVersion,and_(PricingItemVersion.pricing_item_id==latest.c.pricing_item_id,
            PricingItemVersion.version==latest.c.version))
        .where(MemberAccountItem.account_id == account_id).order_by(PricingItem.name)
    )).all()
    return {"items": [{
        "id": link.id, "pricing_item_id": item.id, "name": item.name, "unit": item.unit,
        "unit_price_override": float(link.unit_price_override) if link.unit_price_override is not None else None,
        "mfec_share_type_override": link.mfec_share_type_override,
        "mfec_share_value_override": float(link.mfec_share_value_override) if link.mfec_share_value_override is not None else None,
        "effective_unit_price":float(link.unit_price_override if link.unit_price_override is not None else
            account.default_unit_price_override if account.default_unit_price_override is not None else version.company_unit_price if version else 0),
        "effective_mfec_share_type":link.mfec_share_type_override or account.default_mfec_share_type_override or
            (version.mfec_share_type if version else None),
        "effective_mfec_share_value":float(link.mfec_share_value_override if link.mfec_share_value_override is not None else
            account.default_mfec_share_value_override if account.default_mfec_share_value_override is not None else
            version.mfec_share_value if version else 0),
        "started_at":link.started_at.isoformat() if link.started_at else None,
        "is_active": link.is_active,
    } for link, item, version in rows]}


@router.put("/member-accounts/{account_id}/items")
async def upsert_account_items(
    account_id: int, items: list[AccountItemIn],
    user: UserResponse = Depends(require_permission("financial.member_links.edit")),
    db: AsyncSession = Depends(get_db),
):
    account = await db.get(MemberCompanyAccount, account_id)
    if not account: raise HTTPException(404, "ارتباط العضو غير موجود")
    actor = await resolve_actor_name(db, user)
    existing = {x.pricing_item_id: x for x in (await db.execute(
        select(MemberAccountItem).where(MemberAccountItem.account_id == account_id)
    )).scalars().all()}
    for data in items:
        pricing = await db.get(PricingItem, data.pricing_item_id)
        if not pricing or pricing.company_id != account.company_id:
            raise HTTPException(409, "البند لا يتبع شركة الارتباط")
        row = existing.get(data.pricing_item_id) or MemberAccountItem(account_id=account_id, pricing_item_id=data.pricing_item_id)
        for key, value in data.model_dump().items(): setattr(row, key, value)
        db.add(row)
    add_audit(db, action="member_items.bulk_upsert", entity_type="member_account", entity_id=account_id, actor=actor, new_values=[x.model_dump() for x in items])
    await db.commit()
    return {"saved": len(items)}


@router.get("/member-accounts/{account_id}/annexes")
async def list_annexes(
    account_id:int,_user:UserResponse=Depends(require_any_permission("financial.member_links.view","financial.annexes.manage")),
    db:AsyncSession=Depends(get_db),
):
    rows=(await db.execute(select(MemberAnnex).where(
        MemberAnnex.account_id==account_id,MemberAnnex.deleted_at.is_(None)
    ).order_by(MemberAnnex.uploaded_at.desc()))).scalars().all()
    return {"items":[{"id":x.id,"object_key":x.object_key,"original_filename":x.original_filename,
        "mime_type":x.mime_type,"signed_at":x.signed_at.isoformat() if x.signed_at else None,
        "uploaded_at":x.uploaded_at.isoformat() if x.uploaded_at else None} for x in rows]}


@router.post("/member-accounts/{account_id}/annexes")
async def add_annex(
    account_id:int,data:DocumentMetaIn,user:UserResponse=Depends(require_permission("financial.annexes.manage")),
    db:AsyncSession=Depends(get_db),
):
    if not await db.get(MemberCompanyAccount,account_id):raise HTTPException(404,"ارتباط العضو غير موجود")
    if not data.object_key.startswith("financial/"):raise HTTPException(400,"مسار المستند غير صالح")
    actor=await resolve_actor_name(db,user)
    if data.replaced_id:
        replaced=await db.get(MemberAnnex,data.replaced_id)
        if not replaced or replaced.account_id!=account_id:raise HTTPException(409,"الملحق المستبدل لا يتبع الارتباط")
        replaced.deleted_at=datetime.now();replaced.deleted_by=actor
    row=MemberAnnex(account_id=account_id,object_key=data.object_key,original_filename=data.original_filename,
        mime_type=data.mime_type,size_bytes=data.size_bytes,signed_at=data.signed_at,uploaded_by=actor,replaced_annex_id=data.replaced_id)
    db.add(row);await db.flush()
    add_audit(db,action="annex.create",entity_type="member_annex",entity_id=row.id,actor=actor,new_values=data.model_dump())
    await db.commit();return {"id":row.id}


@router.get("/statements/{statement_id}/attachments")
async def list_statement_attachments(
    statement_id:int,
    _user:UserResponse=Depends(require_any_permission("financial.monthly.view","financial.monthly.enter","financial.monthly.edit")),
    db:AsyncSession=Depends(get_db),
):
    rows=(await db.execute(select(StatementAttachment).where(
        StatementAttachment.statement_id==statement_id,StatementAttachment.deleted_at.is_(None)
    ).order_by(StatementAttachment.uploaded_at.desc()))).scalars().all()
    return {"items":[{"id":x.id,"object_key":x.object_key,"original_filename":x.original_filename,
        "mime_type":x.mime_type,"size_bytes":x.size_bytes,"uploaded_at":x.uploaded_at.isoformat() if x.uploaded_at else None}
        for x in rows]}


@router.post("/statements/{statement_id}/attachments")
async def add_statement_attachment(
    statement_id:int,data:DocumentMetaIn,
    user:UserResponse=Depends(require_any_permission("financial.monthly.enter","financial.monthly.edit")),
    db:AsyncSession=Depends(get_db),
):
    statement=await db.get(MonthlyStatement,statement_id)
    if not statement:raise HTTPException(404,"الكشف غير موجود")
    if statement.status=="approved":raise HTTPException(409,"لا يمكن تعديل مرفقات كشف معتمد")
    if not data.object_key.startswith("financial/"):raise HTTPException(400,"مسار المستند غير صالح")
    actor=await resolve_actor_name(db,user)
    row=StatementAttachment(statement_id=statement_id,object_key=data.object_key,
        original_filename=data.original_filename,mime_type=data.mime_type,size_bytes=data.size_bytes,
        uploaded_by=actor,replaced_attachment_id=data.replaced_id)
    db.add(row);await db.flush()
    add_audit(db,action="statement_attachment.create",entity_type="statement_attachment",entity_id=row.id,actor=actor,new_values=data.model_dump())
    await db.commit();return {"id":row.id}


@router.delete("/statements/{statement_id}/attachments/{attachment_id}")
async def delete_statement_attachment(
    statement_id:int,attachment_id:int,
    user:UserResponse=Depends(require_any_permission("financial.monthly.enter","financial.monthly.edit")),
    db:AsyncSession=Depends(get_db),
):
    statement=await db.get(MonthlyStatement,statement_id)
    row=await db.get(StatementAttachment,attachment_id)
    if not statement or not row or row.statement_id!=statement_id:raise HTTPException(404,"المرفق غير موجود")
    if statement.status=="approved":raise HTTPException(409,"لا يمكن تعديل مرفقات كشف معتمد")
    actor=await resolve_actor_name(db,user);row.deleted_at=datetime.now();row.deleted_by=actor
    add_audit(db,action="statement_attachment.delete",entity_type="statement_attachment",entity_id=row.id,actor=actor)
    await db.commit();return {"id":row.id,"deleted":True}


async def _statement_grid(db: AsyncSession, company_id: int, year: int, month: int):
    period_start = date(year, month, 1)
    period_end = date(year, month, monthrange(year, month)[1])
    statement = (await db.execute(select(MonthlyStatement).where(
        MonthlyStatement.company_id == company_id,
        MonthlyStatement.accounting_year == year, MonthlyStatement.accounting_month == month,
    ))).scalar_one_or_none()
    rows = (await db.execute(
        select(MemberCompanyAccount, MemberAccountItem, Registrations, PricingItem)
        .join(MemberAccountItem, MemberAccountItem.account_id == MemberCompanyAccount.id)
        .join(Registrations, Registrations.id == MemberCompanyAccount.member_id)
        .join(PricingItem, PricingItem.id == MemberAccountItem.pricing_item_id)
        .where(
            MemberCompanyAccount.company_id == company_id, MemberCompanyAccount.deleted_at.is_(None),
            MemberCompanyAccount.status == "active", MemberAccountItem.is_active.is_(True),
            PricingItem.is_active.is_(True), PricingItem.deleted_at.is_(None),
        ).order_by(Registrations.merchant_name, PricingItem.name)
    )).all()
    existing = {}
    if statement:
        existing = {x.member_company_account_id * 10_000_000 + x.pricing_item_id: x for x in (
            await db.execute(select(MonthlyEntryLine).where(MonthlyEntryLine.statement_id == statement.id))
        ).scalars().all()}
    return statement, period_start, period_end, rows, existing


@router.get("/statements/grid")
async def statement_grid(
    company_id: int, accounting_year: int, accounting_month: int,
    user: UserResponse = Depends(require_any_permission("financial.monthly.view", "financial.monthly.enter", "financial.reports.view")),
    db: AsyncSession = Depends(get_db),
):
    statement, _, _, rows, existing = await _statement_grid(db, company_id, accounting_year, accounting_month)
    finance = _is_finance_user(user)
    items = []
    for account, link, member, item in rows:
        old = existing.get(account.id * 10_000_000 + item.id)
        row = {
            "account_item_id": link.id, "account_id": account.id, "member_id": member.id,
            "member_name": member.merchant_name, "business_name": member.business_name,
            "membership_number": member.membership_number, "governorate": member.governorate,
            "registered_name": account.registered_name, "registered_phone": account.registered_phone,
            "customer_code": account.customer_code,
            "customer_portal_url": account.customer_portal_url or account.statement_url,
            "pricing_item_id": item.id, "pricing_item_name": item.name, "unit": item.unit,
            "quantity": float(old.quantity) if old else 0,
            "excluded": bool(old and old.excluded_at),
        }
        if finance and old:
            row.update({
                "company_unit_price_snapshot": float(old.company_unit_price_snapshot),
                "mfec_due_amount": float(old.mfec_due_amount),
                "gross_business_amount": float(old.gross_business_amount),
                "settlement_status": old.settlement_status,
            })
        items.append(row)
    return {"statement_id": statement.id if statement else None, "status": statement.status if statement else "draft", "items": items}


@router.put("/statements/bulk")
async def save_statement_bulk(
    data: StatementBulkIn,
    user: UserResponse = Depends(require_any_permission("financial.monthly.enter", "financial.monthly.edit")),
    db: AsyncSession = Depends(get_db),
):
    actor = await resolve_actor_name(db, user)
    statement, start, end, grid, existing = await _statement_grid(db, data.company_id, data.accounting_year, data.accounting_month)
    if statement and statement.status == "approved":
        raise HTTPException(409, "الكشف معتمد؛ أعد فتحه قبل التعديل")
    if not statement:
        statement = MonthlyStatement(
            company_id=data.company_id, accounting_year=data.accounting_year, accounting_month=data.accounting_month,
            period_start=start, period_end=end, received_at=data.received_at, notes=data.notes, entered_by=actor,
        )
        db.add(statement); await db.flush()
    links = {link.id: (account, link, member, item) for account, link, member, item in grid}
    saved = 0
    for incoming in data.lines:
        if incoming.account_item_id not in links: raise HTTPException(409, "بند ارتباط غير صالح للشركة")
        account, link, member, _item = links[incoming.account_item_id]
        item, version, unit_price, share_type, share_value = await resolve_account_item_pricing(db, link, account, start)
        gross, due = calculate_line(incoming.quantity, unit_price, share_type, share_value)
        row = existing.get(account.id * 10_000_000 + item.id) or MonthlyEntryLine(
            statement_id=statement.id, member_id=member.id, member_company_account_id=account.id,
            pricing_item_id=item.id, pricing_item_version_id=version.id, entered_by=actor, updated_by=actor,
            settlement_status="unsettled",
        )
        row.quantity=incoming.quantity; row.unit_snapshot=item.unit
        row.pricing_item_version_id=version.id; row.company_unit_price_snapshot=unit_price
        row.mfec_share_type_snapshot=share_type; row.mfec_share_value_snapshot=share_value
        row.gross_business_amount=gross; row.mfec_due_amount=due; row.updated_by=actor
        row.excluded_at=datetime.now() if incoming.excluded else None
        row.excluded_by=actor if incoming.excluded else None; row.exclusion_reason=incoming.exclusion_reason
        db.add(row); saved += 1
    add_audit(db, action="statement.bulk_save", entity_type="monthly_statement", entity_id=statement.id, actor=actor, new_values={"saved": saved})
    await db.commit()
    return {"statement_id": statement.id, "status": statement.status, "saved": saved}


@router.post("/statements/{statement_id}/approve")
async def approve_statement(
    statement_id: int,
    user: UserResponse = Depends(require_permission("financial.monthly.approve")),
    db: AsyncSession = Depends(get_db),
):
    statement = await db.get(MonthlyStatement, statement_id)
    if not statement: raise HTTPException(404, "الكشف غير موجود")
    if statement.status == "approved": return {"id": statement.id, "status": statement.status}
    count = (await db.execute(select(func.count(MonthlyEntryLine.id)).where(
        MonthlyEntryLine.statement_id == statement_id, MonthlyEntryLine.excluded_at.is_(None)
    ))).scalar_one()
    if not count: raise HTTPException(409, "لا يمكن اعتماد كشف بلا أسطر")
    actor = await resolve_actor_name(db, user)
    statement.status="approved"; statement.approved_by=actor; statement.approved_at=datetime.now()
    add_audit(db, action="statement.approve", entity_type="monthly_statement", entity_id=statement.id, actor=actor)
    await db.commit()
    return {"id": statement.id, "status": "approved"}


@router.post("/statements/{statement_id}/reopen")
async def reopen_statement(
    statement_id: int, data: ReopenIn,
    user: UserResponse = Depends(require_permission("financial.monthly.reopen")),
    db: AsyncSession = Depends(get_db),
):
    statement = await db.get(MonthlyStatement, statement_id)
    if not statement: raise HTTPException(404, "الكشف غير موجود")
    settled = (await db.execute(select(func.count(MonthlyEntryLine.id)).where(
        MonthlyEntryLine.statement_id == statement_id, MonthlyEntryLine.settlement_status == "settled"
    ))).scalar_one()
    if settled: raise HTTPException(409, "لا يمكن إعادة فتح كشف يحتوي تسويات فعالة")
    actor = await resolve_actor_name(db, user)
    statement.status="draft"; statement.reopened_by=actor; statement.reopened_at=datetime.now(); statement.reopen_reason=data.reason
    add_audit(db, action="statement.reopen", entity_type="monthly_statement", entity_id=statement.id, actor=actor, new_values={"reason": data.reason})
    await db.commit()
    return {"id": statement.id, "status": "draft"}


@router.post("/settlements")
async def create_settlement(
    data: SettlementIn,
    user: UserResponse = Depends(require_permission("financial.settlements.create")),
    db: AsyncSession = Depends(get_db),
):
    actor = await resolve_actor_name(db, user)
    if db.bind and db.bind.dialect.name == "postgresql":
        await db.execute(text("SELECT pg_advisory_xact_lock(hashtext('financial_settlement_sequence'))"))
    lines = (await db.execute(
        select(MonthlyEntryLine, MonthlyStatement)
        .join(MonthlyStatement, MonthlyStatement.id == MonthlyEntryLine.statement_id)
        .where(MonthlyEntryLine.id.in_(data.entry_line_ids))
    )).all()
    if len(lines) != len(set(data.entry_line_ids)): raise HTTPException(404, "بعض أسطر التسوية غير موجودة")
    if any(s.company_id != data.company_id or s.status != "approved" or l.excluded_at for l, s in lines):
        raise HTTPException(409, "كل الأسطر يجب أن تكون من كشف معتمد لنفس الشركة")
    if any(l.settlement_status == "settled" for l, _ in lines): raise HTTPException(409, "بعض الأسطر تمت تسويتها مسبقًا")
    seq = (await db.execute(select(func.count(SettlementBatch.id)).where(
        func.extract("year", SettlementBatch.settled_at) == data.settled_at.year
    ))).scalar_one() + 1
    batch = SettlementBatch(
        batch_number=f"SET-{data.settled_at.year}-{seq:05d}", company_id=data.company_id,
        settled_at=data.settled_at, reference_number=data.reference_number, notes=data.notes,
        attachment_key=data.attachment_key, created_by=actor,
    )
    db.add(batch); await db.flush()
    for line, _ in lines:
        line.settlement_status="settled"
        db.add(SettlementLine(batch_id=batch.id, entry_line_id=line.id, amount_snapshot=line.mfec_due_amount))
    add_audit(db, action="settlement.create", entity_type="settlement_batch", entity_id=batch.id, actor=actor, new_values={"lines": data.entry_line_ids})
    await db.commit()
    return {"id": batch.id, "batch_number": batch.batch_number}


@router.post("/settlements/{batch_id}/reverse")
async def reverse_settlement(
    batch_id: int, data: ReverseIn,
    user: UserResponse = Depends(require_permission("financial.settlements.reverse")),
    db: AsyncSession = Depends(get_db),
):
    batch = await db.get(SettlementBatch, batch_id)
    if not batch: raise HTTPException(404, "دفعة التسوية غير موجودة")
    if batch.status == "reversed": raise HTTPException(409, "تم عكس الدفعة سابقًا")
    allocated = (await db.execute(select(func.count(ReceiptAllocation.id)).where(
        ReceiptAllocation.settlement_batch_id == batch_id
    ))).scalar_one()
    if allocated: raise HTTPException(409, "لا يمكن عكس تسوية مرتبطة بوصل قبض قبل فك التخصيص")
    actor = await resolve_actor_name(db, user)
    line_ids = (await db.execute(select(SettlementLine.entry_line_id).where(SettlementLine.batch_id == batch_id))).scalars().all()
    for line in (await db.execute(select(MonthlyEntryLine).where(MonthlyEntryLine.id.in_(line_ids)))).scalars():
        line.settlement_status="unsettled"
    batch.status="reversed"; db.add(SettlementReversal(batch_id=batch.id, reason=data.reason, reversed_by=actor))
    add_audit(db, action="settlement.reverse", entity_type="settlement_batch", entity_id=batch.id, actor=actor, new_values={"reason": data.reason})
    await db.commit()
    return {"id": batch.id, "status": "reversed"}


@router.get("/settlements")
async def list_settlements(
    company_id: int | None = None,
    _user: UserResponse = Depends(require_permission("financial.settlements.view")),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(SettlementBatch).order_by(SettlementBatch.settled_at.desc(), SettlementBatch.id.desc())
    if company_id: stmt=stmt.where(SettlementBatch.company_id == company_id)
    rows=(await db.execute(stmt)).scalars().all()
    ids=[x.id for x in rows]
    counts={}
    if ids:
        counts=dict((await db.execute(select(SettlementLine.batch_id,func.count(SettlementLine.id)).where(
            SettlementLine.batch_id.in_(ids)).group_by(SettlementLine.batch_id))).all())
    return {"items":[{"id":x.id,"batch_number":x.batch_number,"company_id":x.company_id,
        "settled_at":x.settled_at.isoformat(),"status":x.status,"reference_number":x.reference_number,
        "notes":x.notes,"attachment_key":x.attachment_key,"line_count":counts.get(x.id,0)}
        for x in rows]}


@router.get("/settlements/{batch_id}/lines")
async def settlement_lines(
    batch_id:int,_user:UserResponse=Depends(require_permission("financial.settlements.view")),
    db:AsyncSession=Depends(get_db),
):
    rows=(await db.execute(select(SettlementLine,MonthlyEntryLine,Registrations,PricingItem)
        .join(MonthlyEntryLine,MonthlyEntryLine.id==SettlementLine.entry_line_id)
        .join(Registrations,Registrations.id==MonthlyEntryLine.member_id)
        .join(PricingItem,PricingItem.id==MonthlyEntryLine.pricing_item_id)
        .where(SettlementLine.batch_id==batch_id))).all()
    return {"items":[{"id":sl.id,"entry_line_id":line.id,"member_name":member.merchant_name,
        "membership_number":member.membership_number,"pricing_item":item.name,
        "quantity":float(line.quantity),"amount":float(sl.amount_snapshot)} for sl,line,member,item in rows]}


@router.post("/revenues")
async def create_revenue(
    data: ReceiptIn,
    user: UserResponse = Depends(require_permission("financial.revenues.create")),
    db: AsyncSession = Depends(get_db),
):
    actor=await resolve_actor_name(db,user)
    receipt=RevenueReceipt(**data.model_dump(),created_by=actor,updated_by=actor)
    db.add(receipt); await db.flush()
    add_audit(db,action="revenue.create",entity_type="revenue_receipt",entity_id=receipt.id,actor=actor,new_values=data.model_dump())
    await db.commit()
    return {"id":receipt.id}


@router.get("/revenues")
async def list_revenues(
    company_id:int|None=None, date_from:date|None=None, date_to:date|None=None, include_deleted:bool=False,
    _user:UserResponse=Depends(require_permission("financial.revenues.view")), db:AsyncSession=Depends(get_db),
):
    allocated=select(ReceiptAllocation.receipt_id,func.sum(ReceiptAllocation.allocated_amount).label("allocated")).group_by(ReceiptAllocation.receipt_id).subquery()
    stmt=select(RevenueReceipt,func.coalesce(allocated.c.allocated,0)).outerjoin(allocated,allocated.c.receipt_id==RevenueReceipt.id).order_by(RevenueReceipt.received_at.desc())
    if not include_deleted: stmt=stmt.where(RevenueReceipt.deleted_at.is_(None))
    if company_id: stmt=stmt.where(RevenueReceipt.company_id==company_id)
    if date_from: stmt=stmt.where(RevenueReceipt.received_at>=date_from)
    if date_to: stmt=stmt.where(RevenueReceipt.received_at<=date_to)
    rows=(await db.execute(stmt)).all()
    return {"items":[{"id":x.id,"receipt_number":x.receipt_number,"company_id":x.company_id,
        "received_at":x.received_at.isoformat(),"amount":float(x.amount),"allocated":float(a),
        "remaining":float(money(x.amount)-money(a)),"receipt_method":x.receipt_method,
        "category":x.category,"description":x.description,"period_start":x.period_start.isoformat() if x.period_start else None,
        "period_end":x.period_end.isoformat() if x.period_end else None,"notes":x.notes,
        "attachment_key":x.attachment_key,"deleted":bool(x.deleted_at)} for x,a in rows]}


@router.put("/revenues/{receipt_id}")
async def update_revenue(
    receipt_id:int,data:ReceiptUpdateIn,user:UserResponse=Depends(require_permission("financial.revenues.edit")),
    db:AsyncSession=Depends(get_db),
):
    row=await db.get(RevenueReceipt,receipt_id)
    if not row:raise HTTPException(404,"وصل القبض غير موجود")
    allocated=(await db.execute(select(func.coalesce(func.sum(ReceiptAllocation.allocated_amount),0)).where(
        ReceiptAllocation.receipt_id==receipt_id))).scalar_one()
    if money(data.amount)<money(allocated):raise HTTPException(409,"المبلغ أقل من المبلغ المخصص")
    actor=await resolve_actor_name(db,user)
    old={k:getattr(row,k) for k in data.model_dump()}
    for key,value in data.model_dump().items():setattr(row,key,value)
    row.updated_by=actor
    add_audit(db,action="revenue.update",entity_type="revenue_receipt",entity_id=row.id,actor=actor,old_values=old,new_values=data.model_dump())
    await db.commit();return {"id":row.id}


@router.get("/revenues/{receipt_id}/allocations")
async def list_revenue_allocations(
    receipt_id:int,_user:UserResponse=Depends(require_permission("financial.revenues.view")),
    db:AsyncSession=Depends(get_db),
):
    rows=(await db.execute(select(ReceiptAllocation).where(ReceiptAllocation.receipt_id==receipt_id)
        .order_by(ReceiptAllocation.created_at.desc()))).scalars().all()
    return {"items":[{"id":x.id,"statement_id":x.statement_id,"settlement_batch_id":x.settlement_batch_id,
        "amount":float(x.allocated_amount),"created_at":x.created_at.isoformat() if x.created_at else None} for x in rows]}


@router.get("/revenues/{receipt_id}/allocation-targets")
async def revenue_allocation_targets(
    receipt_id:int,_user:UserResponse=Depends(require_permission("financial.revenues.view")),
    db:AsyncSession=Depends(get_db),
):
    receipt=await db.get(RevenueReceipt,receipt_id)
    if not receipt:raise HTTPException(404,"وصل القبض غير موجود")
    statements=(await db.execute(select(MonthlyStatement).where(
        MonthlyStatement.company_id==receipt.company_id,MonthlyStatement.status=="approved"
    ).order_by(MonthlyStatement.accounting_year.desc(),MonthlyStatement.accounting_month.desc()))).scalars().all()
    batches=(await db.execute(select(SettlementBatch).where(
        SettlementBatch.company_id==receipt.company_id,SettlementBatch.status=="active"
    ).order_by(SettlementBatch.settled_at.desc()))).scalars().all()
    return {"statements":[{"id":x.id,"label":f"{x.accounting_month:02d}/{x.accounting_year}"} for x in statements],
        "settlements":[{"id":x.id,"label":x.batch_number,"settled_at":x.settled_at.isoformat()} for x in batches]}


@router.post("/revenues/{receipt_id}/allocations")
async def allocate_revenue(
    receipt_id:int,data:AllocationIn,user:UserResponse=Depends(require_permission("financial.revenues.edit")),db:AsyncSession=Depends(get_db),
):
    actor=await resolve_actor_name(db,user)
    allocation=await validate_and_add_allocation(db,receipt_id=receipt_id,statement_id=data.statement_id,settlement_batch_id=data.settlement_batch_id,amount=data.amount,actor=actor)
    add_audit(db,action="revenue.allocate",entity_type="revenue_receipt",entity_id=receipt_id,actor=actor,new_values=data.model_dump())
    await db.commit()
    return {"id":allocation.id}


@router.get("/revenues.xlsx")
async def revenues_xlsx(
    company_id:int|None=None,date_from:date|None=None,date_to:date|None=None,
    _user:UserResponse=Depends(require_permission("financial.reports.xlsx")),db:AsyncSession=Depends(get_db),
):
    stmt=select(RevenueReceipt,FinancialCompany).join(FinancialCompany,FinancialCompany.id==RevenueReceipt.company_id).where(
        RevenueReceipt.deleted_at.is_(None))
    if company_id:stmt=stmt.where(RevenueReceipt.company_id==company_id)
    if date_from:stmt=stmt.where(RevenueReceipt.received_at>=date_from)
    if date_to:stmt=stmt.where(RevenueReceipt.received_at<=date_to)
    rows=(await db.execute(stmt.order_by(RevenueReceipt.received_at.desc()))).all()
    payload=build_erp_xlsx([{"receipt":x.receipt_number,"company":c.name,"date":x.received_at.isoformat(),
        "amount":x.amount,"method":x.receipt_method,"category":x.category or "","description":x.description}
        for x,c in rows],[("receipt","رقم الوصل"),("company","الشركة"),("date","التاريخ"),("amount","المبلغ"),
        ("method","طريقة القبض"),("category","التصنيف"),("description","الوصف")],"كشف الإيرادات الفعلية",
        f"الفترة: {date_from or 'البداية'} — {date_to or 'اليوم'}")
    return StreamingResponse(iter([payload]),media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition":'attachment; filename="mfec-revenues.xlsx"'})


@router.delete("/revenues/{receipt_id}")
async def delete_revenue(
    receipt_id:int,user:UserResponse=Depends(require_permission("financial.revenues.delete")),db:AsyncSession=Depends(get_db),
):
    row=await db.get(RevenueReceipt,receipt_id)
    if not row: raise HTTPException(404,"وصل القبض غير موجود")
    actor=await resolve_actor_name(db,user); row.deleted_at=datetime.now(); row.deleted_by=actor
    add_audit(db,action="revenue.delete",entity_type="revenue_receipt",entity_id=row.id,actor=actor,old_values={"amount":row.amount})
    await db.commit(); return {"id":row.id,"deleted":True}


@router.post("/revenues/{receipt_id}/restore")
async def restore_revenue(
    receipt_id:int,user:UserResponse=Depends(require_permission("financial.revenues.restore")),db:AsyncSession=Depends(get_db),
):
    row=await db.get(RevenueReceipt,receipt_id)
    if not row: raise HTTPException(404,"وصل القبض غير موجود")
    actor=await resolve_actor_name(db,user); row.deleted_at=None; row.deleted_by=None; row.restored_at=datetime.now(); row.restored_by=actor
    add_audit(db,action="revenue.restore",entity_type="revenue_receipt",entity_id=row.id,actor=actor)
    await db.commit(); return {"id":row.id,"deleted":False}


@router.delete("/expenses/{expense_id}")
async def soft_delete_expense(
    expense_id:int,user:UserResponse=Depends(require_permission("financial.expenses.delete")),db:AsyncSession=Depends(get_db),
):
    row=await db.get(FinancialExpense,expense_id)
    if not row: raise HTTPException(404,"المصروف غير موجود")
    actor=await resolve_actor_name(db,user); row.deleted_at=datetime.now(); row.deleted_by=actor
    add_audit(db,action="expense.delete",entity_type="expense",entity_id=row.id,actor=actor,old_values={"amount":row.amount})
    await db.commit(); return {"id":row.id,"deleted":True}


@router.post("/expenses/{expense_id}/restore")
async def restore_expense(
    expense_id:int,user:UserResponse=Depends(require_permission("financial.expenses.restore")),db:AsyncSession=Depends(get_db),
):
    row=await db.get(FinancialExpense,expense_id)
    if not row: raise HTTPException(404,"المصروف غير موجود")
    actor=await resolve_actor_name(db,user); row.deleted_at=None; row.deleted_by=None; row.restored_at=datetime.now(); row.restored_by=actor
    add_audit(db,action="expense.restore",entity_type="expense",entity_id=row.id,actor=actor)
    await db.commit(); return {"id":row.id,"deleted":False}


@router.get("/expenses.xlsx")
async def expenses_xlsx(
    accounting_year:int|None=None,accounting_month:int|None=None,date_from:date|None=None,date_to:date|None=None,
    _user:UserResponse=Depends(require_permission("financial.reports.xlsx")),db:AsyncSession=Depends(get_db),
):
    stmt=select(FinancialExpense).where(FinancialExpense.deleted_at.is_(None))
    if accounting_year:stmt=stmt.where(FinancialExpense.accounting_year==accounting_year)
    if accounting_month:stmt=stmt.where(FinancialExpense.accounting_month==accounting_month)
    if date_from:stmt=stmt.where(FinancialExpense.expense_date>=date_from)
    if date_to:stmt=stmt.where(FinancialExpense.expense_date<=date_to)
    rows=(await db.execute(stmt.order_by(FinancialExpense.expense_date.desc()))).scalars().all()
    payload=build_erp_xlsx([{"date":x.expense_date.isoformat(),"category":x.category,"description":x.description,
        "amount":x.amount,"notes":x.notes or "","created_by":x.created_by} for x in rows],
        [("date","التاريخ"),("category","التصنيف"),("description","الوصف"),("amount","المبلغ"),
        ("notes","ملاحظات"),("created_by","المستخدم")],"كشف المصروفات",
        f"الفترة: {accounting_month or 'كل الأشهر'}/{accounting_year or 'كل السنوات'}")
    return StreamingResponse(iter([payload]),media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition":'attachment; filename="mfec-expenses.xlsx"'})


async def _report_lines(
    db:AsyncSession, company_id:int|None, member_id:int|None, service_type_id:int|None,
    pricing_item_id:int|None, governorate:str|None, year:int|None, month:int|None,
    date_from:date|None,date_to:date|None,settlement_status:str|None,selected_ids:list[int]|None,
):
    allocated=select(
        ReceiptAllocation.statement_id,func.sum(ReceiptAllocation.allocated_amount).label("received")
    ).where(ReceiptAllocation.statement_id.is_not(None)).group_by(ReceiptAllocation.statement_id).subquery()
    stmt=(select(MonthlyEntryLine,MonthlyStatement,Registrations,FinancialCompany,ServiceType,PricingItem,func.coalesce(allocated.c.received,0))
          .join(MonthlyStatement,MonthlyStatement.id==MonthlyEntryLine.statement_id)
          .join(Registrations,Registrations.id==MonthlyEntryLine.member_id)
          .join(FinancialCompany,FinancialCompany.id==MonthlyStatement.company_id)
          .join(ServiceType,ServiceType.id==FinancialCompany.service_type_id)
          .join(PricingItem,PricingItem.id==MonthlyEntryLine.pricing_item_id)
          .outerjoin(allocated,allocated.c.statement_id==MonthlyStatement.id)
          .where(MonthlyStatement.status=="approved",MonthlyEntryLine.excluded_at.is_(None)))
    if company_id: stmt=stmt.where(MonthlyStatement.company_id==company_id)
    if member_id: stmt=stmt.where(MonthlyEntryLine.member_id==member_id)
    if service_type_id: stmt=stmt.where(FinancialCompany.service_type_id==service_type_id)
    if pricing_item_id: stmt=stmt.where(MonthlyEntryLine.pricing_item_id==pricing_item_id)
    if governorate: stmt=stmt.where(Registrations.governorate==governorate)
    if year: stmt=stmt.where(MonthlyStatement.accounting_year==year)
    if month: stmt=stmt.where(MonthlyStatement.accounting_month==month)
    if date_from: stmt=stmt.where(MonthlyStatement.period_end>=date_from)
    if date_to: stmt=stmt.where(MonthlyStatement.period_start<=date_to)
    if settlement_status: stmt=stmt.where(MonthlyEntryLine.settlement_status==settlement_status)
    if selected_ids: stmt=stmt.where(MonthlyEntryLine.id.in_(selected_ids))
    rows=(await db.execute(stmt.order_by(FinancialCompany.name,Registrations.merchant_name,PricingItem.name))).all()
    due_by_statement: dict[int, Decimal] = {}
    for line, statement, *_rest in rows:
        due_by_statement[statement.id] = due_by_statement.get(statement.id, Decimal("0")) + money(line.mfec_due_amount)
    output=[]
    for line,statement,member,company,service,item,received in rows:
        statement_due = due_by_statement.get(statement.id, Decimal("0"))
        line_received = (
            money(min(money(received), statement_due) * money(line.mfec_due_amount) / statement_due)
            if statement_due > 0 else Decimal("0")
        )
        output.append({"id":line.id,"statement_id":statement.id,"company_id":company.id,"company_name":company.name,"service_type":service.name,
                       "member_id":member.id,"member_name":member.merchant_name,"business_name":member.business_name,"membership_number":member.membership_number,
                       "governorate":member.governorate,"pricing_item_id":item.id,"pricing_item":item.name,"unit":line.unit_snapshot,
                       "quantity":float(line.quantity),"unit_price":float(line.company_unit_price_snapshot),"gross_business_amount":float(line.gross_business_amount),
                       "mfec_due_amount":float(line.mfec_due_amount),"settlement_status":line.settlement_status,
                       "settled_amount":float(line.mfec_due_amount if line.settlement_status=="settled" else 0),
                       "received_amount":float(line_received),"outstanding_receivable":float(max(money(line.mfec_due_amount)-line_received,Decimal("0")))})
    return output


@router.get("/reports/lines")
async def report_lines(
    company_id:int|None=None,member_id:int|None=None,service_type_id:int|None=None,pricing_item_id:int|None=None,
    governorate:str|None=None,accounting_year:int|None=None,accounting_month:int|None=None,
    date_from:date|None=None,date_to:date|None=None,settlement_status:Literal["settled","unsettled"]|None=None,
    selected_ids:list[int]|None=Query(default=None),
    _user:UserResponse=Depends(require_permission("financial.reports.view")),db:AsyncSession=Depends(get_db),
):
    items=await _report_lines(db,company_id,member_id,service_type_id,pricing_item_id,governorate,accounting_year,accounting_month,date_from,date_to,settlement_status,selected_ids)
    return {"items":items,"totals":{"gross_business_amount":sum(x["gross_business_amount"] for x in items),"mfec_due_amount":sum(x["mfec_due_amount"] for x in items),
        "settled_amount":sum(x["settled_amount"] for x in items),"unsettled_amount":sum(x["mfec_due_amount"]-x["settled_amount"] for x in items),
        "received_amount":sum(x["received_amount"] for x in items),"outstanding_receivable":sum(x["outstanding_receivable"] for x in items)}}


@router.get("/reports/lines.xlsx")
async def report_lines_xlsx(
    company_id:int|None=None,member_id:int|None=None,service_type_id:int|None=None,pricing_item_id:int|None=None,
    governorate:str|None=None,accounting_year:int|None=None,accounting_month:int|None=None,
    date_from:date|None=None,date_to:date|None=None,settlement_status:Literal["settled","unsettled"]|None=None,
    selected_ids:list[int]|None=Query(default=None),
    _user:UserResponse=Depends(require_permission("financial.reports.xlsx")),db:AsyncSession=Depends(get_db),
):
    items=await _report_lines(db,company_id,member_id,service_type_id,pricing_item_id,governorate,
        accounting_year,accounting_month,date_from,date_to,settlement_status,selected_ids)
    mapped=[{"membership_number":x["membership_number"],"member_name":x["member_name"],"governorate":x["governorate"],
             "shipping_operations":x["quantity"] if "شحن" in x["service_type"] else 0,"shipping_revenue":x["mfec_due_amount"] if "شحن" in x["service_type"] else 0,
             "delivery_operations":x["quantity"] if "توصيل" in x["service_type"] else 0,"delivery_revenue":x["mfec_due_amount"] if "توصيل" in x["service_type"] else 0,
             "other_operations":x["quantity"] if not any(s in x["service_type"] for s in ("شحن","توصيل")) else 0,
             "other_revenue":x["mfec_due_amount"] if not any(s in x["service_type"] for s in ("شحن","توصيل")) else 0,
             "total_operations":x["quantity"],"total_revenue":x["mfec_due_amount"]} for x in items]
    payload=build_financial_xlsx(mapped,"كشف الإدارة المالية","حسب الفلاتر والصفوف المحددة")
    return StreamingResponse(iter([payload]),media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition":'attachment; filename="mfec-financial-report.xlsx"'})


@router.get("/dashboard/erp")
async def erp_dashboard(
    accounting_year:int|None=None,accounting_month:int|None=None,date_from:date|None=None,date_to:date|None=None,
    _user:UserResponse=Depends(require_permission("financial.dashboard.view")),db:AsyncSession=Depends(get_db),
):
    items=await _report_lines(db,None,None,None,None,None,accounting_year,accounting_month,date_from,date_to,None,None)
    due=money(sum(Decimal(str(x["mfec_due_amount"])) for x in items))
    receipt_stmt=select(func.coalesce(func.sum(RevenueReceipt.amount),0)).where(RevenueReceipt.deleted_at.is_(None))
    expense_stmt=select(func.coalesce(func.sum(FinancialExpense.amount),0)).where(FinancialExpense.deleted_at.is_(None))
    if accounting_year:
        receipt_stmt=receipt_stmt.where(func.extract("year",RevenueReceipt.received_at)==accounting_year)
        expense_stmt=expense_stmt.where(FinancialExpense.accounting_year==accounting_year)
    if accounting_month:
        receipt_stmt=receipt_stmt.where(func.extract("month",RevenueReceipt.received_at)==accounting_month)
        expense_stmt=expense_stmt.where(FinancialExpense.accounting_month==accounting_month)
    if date_from:
        receipt_stmt=receipt_stmt.where(RevenueReceipt.received_at>=date_from)
        expense_stmt=expense_stmt.where(FinancialExpense.expense_date>=date_from)
    if date_to:
        receipt_stmt=receipt_stmt.where(RevenueReceipt.received_at<=date_to)
        expense_stmt=expense_stmt.where(FinancialExpense.expense_date<=date_to)
    received=(await db.execute(receipt_stmt)).scalar_one()
    expenses=(await db.execute(expense_stmt)).scalar_one()
    received,expenses=money(received),money(expenses)
    by_company:dict[str,dict[str,float]]={}
    by_service:dict[str,dict[str,float]]={}
    for row in items:
        company=by_company.setdefault(row["company_name"],{"gross":0,"due":0,"received":0})
        company["gross"]+=row["gross_business_amount"];company["due"]+=row["mfec_due_amount"];company["received"]+=row["received_amount"]
        service=by_service.setdefault(row["service_type"],{"gross":0,"due":0})
        service["gross"]+=row["gross_business_amount"];service["due"]+=row["mfec_due_amount"]
    return {"accrued_revenue":float(due),"actual_revenue":float(received),"expenses":float(expenses),
            "outstanding_receivable":float(max(due-received,Decimal("0"))),"estimated_profit":float(due-expenses),
            "actual_net_result":float(received-expenses),"gross_business_amount":sum(x["gross_business_amount"] for x in items),
            "by_company":[{"name":name,**values} for name,values in sorted(by_company.items(),key=lambda x:x[1]["due"],reverse=True)],
            "by_service":[{"name":name,**values} for name,values in sorted(by_service.items(),key=lambda x:x[1]["due"],reverse=True)]}
