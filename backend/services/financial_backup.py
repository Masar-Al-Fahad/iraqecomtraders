"""Private, auditable logical backups for application-managed PostgreSQL data.

Restore is intentionally a reviewed request, not an in-process destructive import.
"""
from __future__ import annotations

import gzip
import hashlib
import json
from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import inspect, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import Base
from models.financial import FinancialBackup
from services.supabase_storage import upload_private_financial_bytes


def _json_value(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, bytes):
        return value.hex()
    return value


async def build_logical_backup_payload(db: AsyncSession) -> bytes:
    """Build a gzip JSON logical snapshot without exposing connection credentials."""
    tables: dict[str, list[dict]] = {}
    existing = await db.run_sync(lambda session: set(inspect(session.connection()).get_table_names()))
    for table in Base.metadata.sorted_tables:
        if table.name == FinancialBackup.__tablename__ or table.name not in existing:
            continue
        result = await db.execute(select(table))
        tables[table.name] = [
            {key: _json_value(value) for key, value in row.items()}
            for row in result.mappings().all()
        ]
    raw = json.dumps(
        {"format": "mfec-logical-backup-v1", "created_at": datetime.now(timezone.utc).isoformat(), "tables": tables},
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return gzip.compress(raw, compresslevel=9)


async def create_backup_record(
    db: AsyncSession, *, actor: str, notes: str | None = None, kind: str = "manual"
) -> FinancialBackup:
    content = await build_logical_backup_payload(db)
    now = datetime.now(timezone.utc)
    number = f"BKP-{now:%Y%m%d-%H%M%S}-{uuid4().hex[:6].upper()}"
    object_key = f"financial/backups/{now:%Y/%m}/{number}.json.gz"
    await upload_private_financial_bytes(object_key, content, content_type="application/gzip")
    row = FinancialBackup(
        backup_number=number,
        object_key=object_key,
        kind=kind,
        status="ready",
        notes=notes,
        size_bytes=len(content),
        checksum_sha256=hashlib.sha256(content).hexdigest(),
        created_by=actor,
    )
    db.add(row)
    await db.flush()
    return row
