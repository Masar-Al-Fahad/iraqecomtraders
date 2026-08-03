"""Independent counters: membership (MF-XXXX) and application/request (REQ-XXXX)."""
from __future__ import annotations

import logging
import re
from typing import Optional, Tuple

from sqlalchemy import Integer, String, Column, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import Base
from models.registrations import Registrations

logger = logging.getLogger(__name__)

MF_RE = re.compile(r"^MF-(\d+)$", re.IGNORECASE)
REQ_RE = re.compile(r"^REQ-(\d+)$", re.IGNORECASE)

COUNTER_MEMBERSHIP = "membership"
COUNTER_APPLICATION = "application"


class SystemCounter(Base):
    __tablename__ = "system_counters"
    __table_args__ = {"extend_existing": True}

    name = Column(String(64), primary_key=True, nullable=False)
    value = Column(Integer, nullable=False, default=0)


def format_membership(n: int) -> str:
    return f"MF-{int(n):04d}"


def format_application(n: int) -> str:
    return f"REQ-{int(n):04d}"


async def _max_existing_number(db: AsyncSession, column, pattern: re.Pattern) -> int:
    result = await db.execute(
        select(column).where(column.isnot(None), column != "")
    )
    max_n = 0
    for (raw,) in result.all():
        if not raw:
            continue
        m = pattern.match(str(raw).strip())
        if m:
            max_n = max(max_n, int(m.group(1)))
    return max_n


async def membership_number_in_use(db: AsyncSession, n: int) -> bool:
    candidate = format_membership(n)
    result = await db.execute(
        select(Registrations.id).where(Registrations.membership_number == candidate).limit(1)
    )
    return result.scalar_one_or_none() is not None


async def application_number_in_use(db: AsyncSession, n: int) -> bool:
    candidate = format_application(n)
    result = await db.execute(
        select(Registrations.id).where(Registrations.request_number == candidate).limit(1)
    )
    return result.scalar_one_or_none() is not None


async def ensure_counter(db: AsyncSession, name: str, seed_from_max: int = 0) -> SystemCounter:
    result = await db.execute(select(SystemCounter).where(SystemCounter.name == name))
    counter = result.scalar_one_or_none()
    if counter is None:
        counter = SystemCounter(name=name, value=int(seed_from_max))
        db.add(counter)
        await db.flush()
    return counter


async def ensure_membership_counter(db: AsyncSession) -> None:
    max_existing = await _max_existing_number(db, Registrations.membership_number, MF_RE)
    await ensure_counter(db, COUNTER_MEMBERSHIP, max_existing)


async def ensure_application_counter(db: AsyncSession) -> None:
    # Prefer max(request_number); fall back to max(id) for legacy rows without request_number
    max_req = await _max_existing_number(db, Registrations.request_number, REQ_RE)
    if max_req <= 0:
        result = await db.execute(select(Registrations.id))
        ids = [r[0] for r in result.all() if r[0]]
        max_req = max(ids) if ids else 0
    await ensure_counter(db, COUNTER_APPLICATION, max_req)


async def get_next_counter_value(
    db: AsyncSession,
    name: str,
    in_use_fn,
) -> int:
    result = await db.execute(select(SystemCounter).where(SystemCounter.name == name))
    counter = result.scalar_one_or_none()
    current = int(counter.value) if counter else 0
    n = current + 1
    for _ in range(100000):
        if not await in_use_fn(db, n):
            return n
        n += 1
    return current + 1


async def set_next_counter_value(
    db: AsyncSession,
    name: str,
    next_n: int,
    in_use_fn,
    ensure_fn,
) -> int:
    await ensure_fn(db)
    result = await db.execute(select(SystemCounter).where(SystemCounter.name == name))
    counter = result.scalar_one_or_none()
    new_value = int(next_n) - 1
    if counter is None:
        db.add(SystemCounter(name=name, value=new_value))
    else:
        counter.value = new_value
    await db.flush()
    return next_n


async def allocate_counter_value(
    db: AsyncSession,
    name: str,
    in_use_fn,
    ensure_fn,
    format_fn,
) -> str:
    await ensure_fn(db)
    for _ in range(100000):
        result = await db.execute(select(SystemCounter).where(SystemCounter.name == name))
        counter = result.scalar_one_or_none()
        if counter is None:
            counter = SystemCounter(name=name, value=0)
            db.add(counter)
            await db.flush()

        counter.value = int(counter.value or 0) + 1
        n = int(counter.value)
        await db.flush()
        if not await in_use_fn(db, n):
            code = format_fn(n)
            logger.info("Allocated %s counter=%s -> %s", name, n, code)
            return code
    raise RuntimeError("تعذر تخصيص رقم فريد")


# ---- Membership API ----
async def get_next_membership_number(db: AsyncSession) -> int:
    await ensure_membership_counter(db)
    return await get_next_counter_value(db, COUNTER_MEMBERSHIP, membership_number_in_use)


async def set_next_membership_number(db: AsyncSession, next_n: int) -> int:
    if next_n < 1 or next_n > 999999:
        raise ValueError("رقم العضوية يجب أن يكون بين 1 و 999999")
    if await membership_number_in_use(db, next_n):
        raise ValueError("رقم العضوية مستخدم بالفعل، يرجى اختيار رقم آخر.")
    return await set_next_counter_value(
        db, COUNTER_MEMBERSHIP, next_n, membership_number_in_use, ensure_membership_counter
    )


async def allocate_membership_number(db: AsyncSession) -> str:
    return await allocate_counter_value(
        db,
        COUNTER_MEMBERSHIP,
        membership_number_in_use,
        ensure_membership_counter,
        format_membership,
    )


# ---- Application / request API ----
async def get_next_application_number(db: AsyncSession) -> int:
    await ensure_application_counter(db)
    return await get_next_counter_value(db, COUNTER_APPLICATION, application_number_in_use)


async def set_next_application_number(db: AsyncSession, next_n: int) -> int:
    if next_n < 1 or next_n > 999999:
        raise ValueError("رقم الطلب يجب أن يكون بين 1 و 999999")
    if await application_number_in_use(db, next_n):
        raise ValueError("رقم الطلب مستخدم بالفعل، يرجى اختيار رقم آخر.")
    return await set_next_counter_value(
        db, COUNTER_APPLICATION, next_n, application_number_in_use, ensure_application_counter
    )


async def allocate_application_number(db: AsyncSession) -> str:
    return await allocate_counter_value(
        db,
        COUNTER_APPLICATION,
        application_number_in_use,
        ensure_application_counter,
        format_application,
    )
