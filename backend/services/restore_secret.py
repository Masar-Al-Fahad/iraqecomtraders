"""Hashed restore-confirmation secret stored in app_settings (never returned plaintext)."""
from __future__ import annotations

import hashlib
import json
import secrets
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from services.app_settings_service import get_setting_raw, save_setting
from services.financial import add_audit

KEY_RESTORE_SECRET = "backup_restore_confirmation"


def _hash_secret(value: str) -> str:
    normalized = (value or "").strip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


async def _load_payload(db: AsyncSession) -> dict[str, Any]:
    try:
        row = await get_setting_raw(db, KEY_RESTORE_SECRET)
    except Exception:
        # Missing app_settings table (e.g. partial test DB) → treat as unset.
        return {}
    if not row or not row.value:
        return {}
    try:
        data = json.loads(row.value)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


async def restore_secret_status(db: AsyncSession) -> dict[str, Any]:
    raw = await _load_payload(db)
    configured = bool(raw.get("hash"))
    return {
        "configured": configured,
        "updated_at": raw.get("updated_at"),
        "updated_by": raw.get("updated_by"),
        "legacy_fallback_enabled": False,
        "message": (
            "رمز تأكيد مخصص مفعّل. لن يُعرض نص الرمز بعد الحفظ."
            if configured
            else "لم يُضبط رمز تأكيد الاستعادة بعد. يجب تعيين رمز من حساب مخوّل قبل أي طلب استعادة."
        ),
    }


async def set_restore_secret(
    db: AsyncSession,
    *,
    new_secret: str,
    actor: str,
) -> dict[str, Any]:
    secret = (new_secret or "").strip()
    if len(secret) < 6:
        raise HTTPException(400, "رمز التأكيد يجب ألا يقل عن 6 أحرف")
    payload = {
        "hash": _hash_secret(secret),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "updated_by": actor,
    }
    await save_setting(db, KEY_RESTORE_SECRET, payload, actor)
    add_audit(
        db,
        action="backup.restore_secret_changed",
        entity_type="app_settings",
        entity_id=None,
        actor=actor,
        new_values={"configured": True},
        # Never store plaintext secret in audit.
    )
    await db.commit()
    return {"ok": True, "configured": True, "message": "تم حفظ رمز تأكيد الاستعادة (لن يُعرض نصه مرة أخرى)."}


async def verify_restore_confirmation(db: AsyncSession, confirmation: str) -> None:
    """Require a configured hashed secret. No hardcoded fallback (e.g. RESTORE)."""
    given = (confirmation or "").strip()
    if not given:
        raise HTTPException(400, "رمز تأكيد الاستعادة مطلوب")
    raw = await _load_payload(db)
    stored_hash = raw.get("hash")
    if not stored_hash:
        raise HTTPException(
            400,
            "لم يُضبط رمز تأكيد الاستعادة بعد. عيّن الرمز من إعدادات النسخ الاحتياطية قبل طلب الاستعادة.",
        )
    if not secrets.compare_digest(_hash_secret(given), str(stored_hash)):
        raise HTTPException(400, "رمز تأكيد الاستعادة غير صحيح")
