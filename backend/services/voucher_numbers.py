"""Independent voucher sequences: REC-N (receipts) and PAY-N (payments/expenses)."""
from __future__ import annotations

import re

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.financial import FinancialExpense, RevenueReceipt
from services.membership_numbers import (
    SystemCounter,
    allocate_counter_value,
    ensure_counter,
    get_next_counter_value,
    set_next_counter_value,
)

COUNTER_RECEIPT = "financial_rec"
COUNTER_PAYMENT = "financial_pay"

REC_RE = re.compile(r"^REC-(\d+)$", re.IGNORECASE)
PAY_RE = re.compile(r"^PAY-(\d+)$", re.IGNORECASE)


def format_receipt(n: int) -> str:
    return f"REC-{int(n):04d}"


def format_payment(n: int) -> str:
    return f"PAY-{int(n):04d}"


def parse_receipt_suffix(code: str | None) -> int | None:
    if not code:
        return None
    m = REC_RE.match(str(code).strip())
    return int(m.group(1)) if m else None


def parse_payment_suffix(code: str | None) -> int | None:
    if not code:
        return None
    m = PAY_RE.match(str(code).strip())
    return int(m.group(1)) if m else None


async def _max_receipt_suffix(db: AsyncSession) -> int:
    rows = (await db.execute(select(RevenueReceipt.receipt_number))).scalars().all()
    max_n = 0
    for raw in rows:
        n = parse_receipt_suffix(raw)
        if n:
            max_n = max(max_n, n)
    return max_n


async def _max_payment_suffix(db: AsyncSession) -> int:
    rows = (await db.execute(select(FinancialExpense.payment_number))).scalars().all()
    max_n = 0
    for raw in rows:
        n = parse_payment_suffix(raw)
        if n:
            max_n = max(max_n, n)
    return max_n


async def receipt_number_in_use(db: AsyncSession, n: int) -> bool:
    code = format_receipt(n)
    row = (await db.execute(
        select(RevenueReceipt.id).where(RevenueReceipt.receipt_number == code).limit(1)
    )).scalar_one_or_none()
    return row is not None


async def payment_number_in_use(db: AsyncSession, n: int) -> bool:
    code = format_payment(n)
    row = (await db.execute(
        select(FinancialExpense.id).where(FinancialExpense.payment_number == code).limit(1)
    )).scalar_one_or_none()
    return row is not None


async def ensure_receipt_counter(db: AsyncSession) -> SystemCounter:
    existing = (await db.execute(
        select(SystemCounter).where(SystemCounter.name == COUNTER_RECEIPT)
    )).scalar_one_or_none()
    if existing is not None:
        return existing
    return await ensure_counter(db, COUNTER_RECEIPT, await _max_receipt_suffix(db))


async def ensure_payment_counter(db: AsyncSession) -> SystemCounter:
    existing = (await db.execute(
        select(SystemCounter).where(SystemCounter.name == COUNTER_PAYMENT)
    )).scalar_one_or_none()
    if existing is not None:
        return existing
    return await ensure_counter(db, COUNTER_PAYMENT, await _max_payment_suffix(db))


async def peek_next_receipt_number(db: AsyncSession) -> int:
    counter = await ensure_receipt_counter(db)
    return await get_next_counter_value(db, COUNTER_RECEIPT, receipt_number_in_use, counter=counter)


async def peek_next_payment_number(db: AsyncSession) -> int:
    counter = await ensure_payment_counter(db)
    return await get_next_counter_value(db, COUNTER_PAYMENT, payment_number_in_use, counter=counter)


async def set_next_receipt_number(db: AsyncSession, next_n: int) -> int:
    if next_n < 1 or next_n > 9_999_999:
        raise HTTPException(400, "رقم وصل القبض التالي يجب أن يكون بين 1 و 9999999")
    if await receipt_number_in_use(db, next_n):
        raise HTTPException(409, f"الرقم {format_receipt(next_n)} مستخدم بالفعل ولا يمكن تعيينه كتالي")
    return await set_next_counter_value(
        db, COUNTER_RECEIPT, next_n, receipt_number_in_use, ensure_receipt_counter
    )


async def set_next_payment_number(db: AsyncSession, next_n: int) -> int:
    if next_n < 1 or next_n > 9_999_999:
        raise HTTPException(400, "رقم وصل الصرف التالي يجب أن يكون بين 1 و 9999999")
    if await payment_number_in_use(db, next_n):
        raise HTTPException(409, f"الرقم {format_payment(next_n)} مستخدم بالفعل ولا يمكن تعيينه كتالي")
    return await set_next_counter_value(
        db, COUNTER_PAYMENT, next_n, payment_number_in_use, ensure_payment_counter
    )


async def allocate_receipt_number(db: AsyncSession) -> str:
    await ensure_receipt_counter(db)
    return await allocate_counter_value(
        db,
        COUNTER_RECEIPT,
        receipt_number_in_use,
        ensure_receipt_counter,
        format_receipt,
        skip_in_use_check=False,
    )


async def allocate_payment_number(db: AsyncSession) -> str:
    await ensure_payment_counter(db)
    return await allocate_counter_value(
        db,
        COUNTER_PAYMENT,
        payment_number_in_use,
        ensure_payment_counter,
        format_payment,
        skip_in_use_check=False,
    )
