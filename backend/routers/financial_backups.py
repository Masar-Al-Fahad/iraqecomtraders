"""Secure backup catalog and reviewed restore-request workflow."""
from __future__ import annotations

import hashlib
from datetime import datetime
from io import BytesIO

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from dependencies.permissions import require_permission
from models.financial import FinancialBackup
from schemas.auth import UserResponse
from services.actor import resolve_actor_name
from services.financial import add_audit
from services.financial_backup import create_backup_record
from services.supabase_storage import (
    delete_private_financial_object,
    download_private_financial_bytes,
)

router = APIRouter(prefix="/api/v1/admin/financial/backups", tags=["financial-backups"])


class BackupCreateIn(BaseModel):
    notes: str | None = Field(default=None, max_length=1000)


class RestoreRequestIn(BaseModel):
    confirmation: str
    notes: str | None = Field(default=None, max_length=1000)


def _item(row: FinancialBackup) -> dict:
    return {
        "id": row.id,
        "backup_number": row.backup_number,
        "kind": row.kind,
        "status": row.status,
        "notes": row.notes,
        "size_bytes": row.size_bytes,
        "checksum_sha256": row.checksum_sha256,
        "created_by": row.created_by,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "restore_requested_by": row.restore_requested_by,
        "restore_requested_at": row.restore_requested_at.isoformat() if row.restore_requested_at else None,
        "pre_restore_backup_id": row.pre_restore_backup_id,
        "deleted": bool(row.deleted_at),
    }


@router.get("")
async def list_backups(
    include_deleted: bool = False,
    _user: UserResponse = Depends(require_permission("backups.view")),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(FinancialBackup)
    if not include_deleted:
        stmt = stmt.where(FinancialBackup.deleted_at.is_(None))
    rows = (await db.execute(stmt.order_by(FinancialBackup.created_at.desc()))).scalars().all()
    return {"items": [_item(row) for row in rows]}


@router.post("")
async def create_backup(
    data: BackupCreateIn,
    user: UserResponse = Depends(require_permission("backups.create")),
    db: AsyncSession = Depends(get_db),
):
    actor = await resolve_actor_name(db, user)
    row = await create_backup_record(db, actor=actor, notes=data.notes)
    add_audit(db, action="backup.create", entity_type="financial_backup", entity_id=row.id, actor=actor)
    await db.commit()
    return _item(row)


@router.get("/{backup_id}/download")
async def download_backup(
    backup_id: int,
    _user: UserResponse = Depends(require_permission("backups.download")),
    db: AsyncSession = Depends(get_db),
):
    row = await db.get(FinancialBackup, backup_id)
    if not row or row.deleted_at:
        raise HTTPException(404, "النسخة الاحتياطية غير موجودة")
    content, _ = await download_private_financial_bytes(row.object_key)
    if hashlib.sha256(content).hexdigest() != row.checksum_sha256:
        raise HTTPException(409, "فشل التحقق من سلامة النسخة الاحتياطية")
    return StreamingResponse(
        BytesIO(content),
        media_type="application/gzip",
        headers={"Content-Disposition": f'attachment; filename="{row.backup_number}.json.gz"'},
    )


@router.post("/{backup_id}/restore-request")
async def request_restore(
    backup_id: int,
    data: RestoreRequestIn,
    user: UserResponse = Depends(require_permission("backups.restore")),
    db: AsyncSession = Depends(get_db),
):
    if data.confirmation != "RESTORE":
        raise HTTPException(400, "اكتب RESTORE حرفيًا لتأكيد طلب الاستعادة")
    if not (data.notes or "").strip():
        raise HTTPException(400, "سبب الاستعادة مطلوب")
    target = await db.get(FinancialBackup, backup_id)
    if not target or target.deleted_at or target.status not in {"ready", "restore_requested"}:
        raise HTTPException(409, "النسخة غير متاحة للاستعادة")
    actor = await resolve_actor_name(db, user)
    pre = await create_backup_record(
        db,
        actor=actor,
        notes=f"نسخة تلقائية قبل طلب استعادة {target.backup_number}",
        kind="pre_restore",
    )
    target.status = "restore_requested"
    target.restore_requested_by = actor
    target.restore_requested_at = datetime.now()
    target.pre_restore_backup_id = pre.id
    add_audit(
        db,
        action="backup.restore_requested",
        entity_type="financial_backup",
        entity_id=target.id,
        actor=actor,
        new_values={"pre_restore_backup_id": pre.id, "notes": data.notes},
    )
    await db.commit()
    return {"id": target.id, "status": target.status, "pre_restore_backup_id": pre.id}


@router.delete("/{backup_id}")
async def delete_backup(
    backup_id: int,
    user: UserResponse = Depends(require_permission("backups.delete")),
    db: AsyncSession = Depends(get_db),
):
    row = await db.get(FinancialBackup, backup_id)
    if not row or row.deleted_at:
        raise HTTPException(404, "النسخة الاحتياطية غير موجودة")
    actor = await resolve_actor_name(db, user)
    await delete_private_financial_object(row.object_key)
    row.deleted_at = datetime.now()
    row.deleted_by = actor
    row.status = "deleted"
    add_audit(db, action="backup.delete", entity_type="financial_backup", entity_id=row.id, actor=actor)
    await db.commit()
    return {"id": row.id, "deleted": True}
