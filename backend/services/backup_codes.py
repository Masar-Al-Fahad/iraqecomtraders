"""One-time backup recovery codes for panel users (hashed at rest)."""
from __future__ import annotations

import hashlib
import logging
import secrets
import uuid
from datetime import datetime
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from models.backup_codes import PanelUserBackupCode
from models.panel_users import PanelUser
from services.financial import add_audit
from services.panel_auth import hash_password

logger = logging.getLogger(__name__)

CODE_COUNT = 5
# Human-friendly: XXXX-XXXX-XXXX (A-Z0-9 without ambiguous chars)
_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def _generate_plain_code() -> str:
    parts = []
    for _ in range(3):
        parts.append("".join(secrets.choice(_ALPHABET) for _ in range(4)))
    return "-".join(parts)


def _hash_code(code: str) -> str:
    # Dedicated hash (not password-hash format) so we can use hmac compare
    normalized = (code or "").strip().upper().replace(" ", "")
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return digest


def _codes_match(plain: str, stored_hash: str) -> bool:
    return secrets.compare_digest(_hash_code(plain), (stored_hash or "").strip())


async def generate_backup_codes(
    db: AsyncSession,
    *,
    user: PanelUser,
    actor: str,
) -> dict[str, Any]:
    batch_id = str(uuid.uuid4())
    now = datetime.utcnow()
    # Revoke previous unused codes
    await db.execute(
        update(PanelUserBackupCode)
        .where(
            PanelUserBackupCode.user_id == user.id,
            PanelUserBackupCode.used_at.is_(None),
            PanelUserBackupCode.revoked_at.is_(None),
        )
        .values(revoked_at=now)
    )
    plains: list[str] = []
    for _ in range(CODE_COUNT):
        plain = _generate_plain_code()
        plains.append(plain)
        db.add(
            PanelUserBackupCode(
                user_id=user.id,
                batch_id=batch_id,
                code_hash=_hash_code(plain),
                created_at=now,
                created_by=actor,
            )
        )
    add_audit(
        db,
        action="backup_codes.generated",
        entity_type="panel_user",
        entity_id=user.id,
        actor=actor,
        new_values={"batch_id": batch_id, "count": CODE_COUNT},
    )
    await db.commit()
    return {
        "ok": True,
        "user_id": user.id,
        "username": user.username,
        "batch_id": batch_id,
        "codes": plains,
        "message": "احفظ هذه الرموز الآن — لن تُعرض مرة أخرى. كل رمز يُستخدم مرة واحدة فقط.",
    }


async def backup_codes_status(db: AsyncSession, user_id: int) -> dict[str, Any]:
    rows = (
        await db.execute(select(PanelUserBackupCode).where(PanelUserBackupCode.user_id == user_id))
    ).scalars().all()
    active = [r for r in rows if r.used_at is None and r.revoked_at is None]
    used = [r for r in rows if r.used_at is not None]
    revoked = [r for r in rows if r.revoked_at is not None and r.used_at is None]
    latest_batch = active[0].batch_id if active else (rows[-1].batch_id if rows else None)
    return {
        "user_id": user_id,
        "remaining": len(active),
        "used": len(used),
        "revoked": len(revoked),
        "latest_batch_id": latest_batch,
        "has_active_codes": len(active) > 0,
    }


async def consume_backup_code_and_reset_password(
    db: AsyncSession,
    *,
    username: str,
    code: str,
    new_password: str,
    request_ip: str | None = None,
) -> dict[str, Any]:
    username = (username or "").strip()
    code = (code or "").strip()
    if not username or not code:
        raise HTTPException(400, "اسم المستخدم والرمز الاحتياطي مطلوبان")
    if len(new_password or "") < 6:
        raise HTTPException(400, "كلمة المرور الجديدة يجب ألا تقل عن 6 أحرف")

    user = (await db.execute(select(PanelUser).where(PanelUser.username == username))).scalar_one_or_none()
    # Always generic failure to reduce enumeration
    generic = HTTPException(400, "تعذر التحقق من الرمز الاحتياطي أو بيانات الطلب")
    if not user or not user.is_active:
        add_audit(
            db, action="backup_codes.reset_unknown", entity_type="panel_user", entity_id=None,
            actor=username, new_values={"ip": request_ip},
        )
        await db.commit()
        raise generic

    rows = (
        await db.execute(
            select(PanelUserBackupCode).where(
                PanelUserBackupCode.user_id == user.id,
                PanelUserBackupCode.used_at.is_(None),
                PanelUserBackupCode.revoked_at.is_(None),
            )
        )
    ).scalars().all()

    matched: PanelUserBackupCode | None = None
    for row in rows:
        if _codes_match(code, row.code_hash):
            matched = row
            break
    if not matched:
        add_audit(
            db, action="backup_codes.reset_failed", entity_type="panel_user", entity_id=user.id,
            actor=username, new_values={"ip": request_ip},
        )
        await db.commit()
        raise generic

    matched.used_at = datetime.utcnow()
    user.password_hash = hash_password(new_password)
    user.updated_at = datetime.utcnow()
    add_audit(
        db, action="backup_codes.used_reset", entity_type="panel_user", entity_id=user.id,
        actor=username, new_values={"ip": request_ip, "batch_id": matched.batch_id},
    )
    await db.commit()
    return {"ok": True, "message": "تم تحديث كلمة المرور. الرمز الاحتياطي لم يعد صالحًا."}


async def admin_set_password(
    db: AsyncSession,
    *,
    user: PanelUser,
    new_password: str,
    actor: str,
) -> dict[str, Any]:
    if len(new_password or "") < 6:
        raise HTTPException(400, "كلمة المرور الجديدة يجب ألا تقل عن 6 أحرف")
    if getattr(user, "is_super_admin", False) and actor != user.username:
        # Allow super admin to reset others including another super? Only non-self supers blocked lightly
        pass
    user.password_hash = hash_password(new_password)
    user.updated_at = datetime.utcnow()
    add_audit(
        db, action="panel_user.password_set", entity_type="panel_user", entity_id=user.id,
        actor=actor, new_values={"by_admin": True},
    )
    await db.commit()
    return {"ok": True, "message": "تم تحديث كلمة المرور", "user_id": user.id, "username": user.username}
