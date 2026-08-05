"""Independent counters: membership (MF-XXXX) and application/request (REQ-XXXX)."""
from __future__ import annotations

import logging
import re
from typing import Optional

from sqlalchemy import Integer, String, Column, cast, func, select
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


async def _max_existing_number(db: AsyncSession, column, pattern: re.Pattern, prefix: str) -> int:
    """Return max numeric suffix for MF-/REQ- codes via SQL aggregate (no full-table Python scan)."""
    # substr is 1-based; skip "MF-" / "REQ-" (3 chars) → start at 4
    num_expr = cast(func.substr(column, 4), Integer)
    dialect = ""
    try:
        conn = await db.connection()
        dialect = conn.dialect.name
    except Exception:
        dialect = ""

    if dialect == "postgresql":
        # Case-insensitive prefix + digits only (avoids cast errors on junk values)
        result = await db.execute(
            select(func.coalesce(func.max(num_expr), 0)).where(
                column.isnot(None),
                column != "",
                column.op("~*")(rf"^{re.escape(prefix)}[0-9]+$"),
            )
        )
        return int(result.scalar() or 0)

    # SQLite / others: LIKE then validate in Python on the matching subset
    result = await db.execute(
        select(column).where(column.isnot(None), column != "", column.ilike(f"{prefix}%"))
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


async def ensure_membership_counter(db: AsyncSession) -> SystemCounter:
    """Return membership counter; seed from MAX(MF-*) only when the row is missing."""
    result = await db.execute(
        select(SystemCounter).where(SystemCounter.name == COUNTER_MEMBERSHIP)
    )
    counter = result.scalar_one_or_none()
    if counter is not None:
        return counter
    max_existing = await _max_existing_number(
        db, Registrations.membership_number, MF_RE, "MF-"
    )
    return await ensure_counter(db, COUNTER_MEMBERSHIP, max_existing)


async def ensure_application_counter(db: AsyncSession) -> SystemCounter:
    """Return application counter; seed from MAX(REQ-*) / max(id) only when missing."""
    result = await db.execute(
        select(SystemCounter).where(SystemCounter.name == COUNTER_APPLICATION)
    )
    counter = result.scalar_one_or_none()
    if counter is not None:
        return counter
    max_req = await _max_existing_number(db, Registrations.request_number, REQ_RE, "REQ-")
    if max_req <= 0:
        result = await db.execute(select(func.coalesce(func.max(Registrations.id), 0)))
        max_req = int(result.scalar() or 0)
    return await ensure_counter(db, COUNTER_APPLICATION, max_req)


async def get_next_counter_value(
    db: AsyncSession,
    name: str,
    in_use_fn,
    counter: Optional[SystemCounter] = None,
) -> int:
    if counter is None:
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
    counter = await ensure_fn(db)
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
    """Atomically increment system_counters (no full-table scan of registrations).

    Happy path: UPDATE … RETURNING + indexed point existence check.
    Replaces select-row → mutate → flush → exists (extra round trips).
    """
    from sqlalchemy import text

    from services import reg_perf

    for _ in range(100000):
        with reg_perf.stage("counter_select_increment"):
            result = await db.execute(
                text(
                    "UPDATE system_counters SET value = value + 1 "
                    "WHERE name = :name RETURNING value"
                ),
                {"name": name},
            )
            row = result.first()
            if row is None:
                with reg_perf.stage("counter_ensure"):
                    await ensure_fn(db)
                continue
            n = int(row[0])
        with reg_perf.stage("counter_in_use_check"):
            taken = await in_use_fn(db, n)
        if not taken:
            code = format_fn(n)
            logger.info("Allocated %s counter=%s -> %s", name, n, code)
            return code
    raise RuntimeError("تعذر تخصيص رقم فريد")


# ---- Membership API ----
async def get_next_membership_number(db: AsyncSession) -> int:
    counter = await ensure_membership_counter(db)
    return await get_next_counter_value(
        db, COUNTER_MEMBERSHIP, membership_number_in_use, counter=counter
    )


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
    counter = await ensure_application_counter(db)
    return await get_next_counter_value(
        db, COUNTER_APPLICATION, application_number_in_use, counter=counter
    )


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
