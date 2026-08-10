"""Core accounting rules for MFEC financial ERP."""
from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.financial import (
    MemberAccountItem, MemberCompanyAccount, MonthlyStatement, PricingItem,
    PricingItemVersion, ReceiptAllocation, RevenueReceipt, SettlementBatch,
)

MONEY = Decimal("0.001")


def money(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(MONEY, rounding=ROUND_HALF_UP)


def calculate_line(quantity, unit_price, share_type: str, share_value) -> tuple[Decimal, Decimal]:
    qty, price, share = money(quantity), money(unit_price), money(share_value)
    if qty < 0 or price < 0 or share < 0:
        raise ValueError("القيم المالية لا يمكن أن تكون سالبة")
    gross = money(qty * price)
    if share_type == "fixed":
        due = money(qty * share)
    elif share_type == "percentage":
        due = money(gross * share / Decimal("100"))
    else:
        raise ValueError("نوع حصة MFEC غير مدعوم")
    return gross, due


async def active_pricing_version(db: AsyncSession, item_id: int, on_date: date) -> PricingItemVersion:
    row = (await db.execute(
        select(PricingItemVersion).where(
            PricingItemVersion.pricing_item_id == item_id,
            PricingItemVersion.effective_from <= on_date,
            or_(PricingItemVersion.effective_to.is_(None), PricingItemVersion.effective_to >= on_date),
        ).order_by(PricingItemVersion.effective_from.desc(), PricingItemVersion.version.desc()).limit(1)
    )).scalar_one_or_none()
    if not row:
        raise HTTPException(400, "لا يوجد سعر فعال للبند في فترة الكشف")
    return row


async def resolve_account_item_pricing(
    db: AsyncSession, link: MemberAccountItem, account: MemberCompanyAccount, on_date: date
) -> tuple[PricingItem, PricingItemVersion, Decimal, str, Decimal]:
    item = await db.get(PricingItem, link.pricing_item_id)
    if not item or item.deleted_at or not item.is_active:
        raise HTTPException(400, "بند التحاسب غير فعال")
    version = await active_pricing_version(db, item.id, on_date)
    unit_price = (
        link.unit_price_override
        if link.unit_price_override is not None
        else account.default_unit_price_override
        if account.default_unit_price_override is not None
        else version.company_unit_price
    )
    share_type = (
        link.mfec_share_type_override
        or account.default_mfec_share_type_override
        or version.mfec_share_type
    )
    share_value = (
        link.mfec_share_value_override
        if link.mfec_share_value_override is not None
        else account.default_mfec_share_value_override
        if account.default_mfec_share_value_override is not None
        else version.mfec_share_value
    )
    return item, version, money(unit_price), share_type, money(share_value)


async def validate_and_add_allocation(
    db: AsyncSession,
    *,
    receipt_id: int,
    statement_id: int | None,
    settlement_batch_id: int | None,
    amount: Decimal,
    actor: str,
) -> ReceiptAllocation:
    """Serialize allocations for a receipt and enforce one-company/amount rules."""
    stmt = select(RevenueReceipt).where(RevenueReceipt.id == receipt_id)
    if db.bind and db.bind.dialect.name == "postgresql":
        stmt = stmt.with_for_update()
    receipt = (await db.execute(stmt)).scalar_one_or_none()
    if not receipt or receipt.deleted_at:
        raise HTTPException(404, "وصل القبض غير موجود")
    if bool(statement_id) == bool(settlement_batch_id):
        raise HTTPException(400, "يجب تحديد كشف أو دفعة تسوية واحدة")
    target_company = None
    if statement_id:
        statement = await db.get(MonthlyStatement, statement_id)
        target_company = statement.company_id if statement else None
    else:
        batch = await db.get(SettlementBatch, settlement_batch_id)
        target_company = batch.company_id if batch else None
    if target_company is None:
        raise HTTPException(404, "هدف التخصيص غير موجود")
    if target_company != receipt.company_id:
        raise HTTPException(409, "لا يمكن توزيع الوصل على شركة مختلفة")
    allocated = (await db.execute(
        select(func.coalesce(func.sum(ReceiptAllocation.allocated_amount), 0))
        .where(ReceiptAllocation.receipt_id == receipt.id)
    )).scalar_one()
    amount = money(amount)
    if amount <= 0 or money(allocated) + amount > money(receipt.amount):
        raise HTTPException(409, "مبلغ التخصيص يتجاوز الرصيد المتاح في الوصل")
    allocation = ReceiptAllocation(
        receipt_id=receipt.id, statement_id=statement_id,
        settlement_batch_id=settlement_batch_id, allocated_amount=amount, created_by=actor,
    )
    db.add(allocation)
    await db.flush()
    return allocation
