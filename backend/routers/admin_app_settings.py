"""Admin + public APIs for brand and registration form settings."""
from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from dependencies.permissions import require_permission
from routers.audit_log import log_action
from schemas.auth import UserResponse
from services.app_settings_service import (
    DEFAULT_BRAND,
    DEFAULT_REG_FORM,
    KEY_BRAND,
    KEY_REG_FORM,
    get_brand_settings,
    get_registration_form_settings,
    save_setting,
)
from services.panel_auth import ensure_schema
from services import supabase_storage as s3store

logger = logging.getLogger(__name__)

admin_router = APIRouter(prefix="/api/v1/admin/app-settings", tags=["app-settings"])
public_router = APIRouter(prefix="/api/v1/public/app-settings", tags=["public-app-settings"])



def _actor(user: UserResponse) -> str:
    return user.name or user.email or "admin"


class SettingsPayload(BaseModel):
    settings: Dict[str, Any]


@public_router.get("/brand")
async def public_brand(db: AsyncSession = Depends(get_db)):
    await ensure_schema()
    return await get_brand_settings(db)


@public_router.get("/registration-form")
async def public_registration_form(db: AsyncSession = Depends(get_db)):
    await ensure_schema()
    return await get_registration_form_settings(db)


@public_router.get("/brand-file/{object_key:path}")
async def public_brand_file(object_key: str):
    safe = object_key.replace("\\", "/").lstrip("/")
    if ".." in safe.split("/"):
        raise HTTPException(status_code=400, detail="مسار غير صالح")
    # Accept legacy bare filenames and brand/… keys
    storage_key = s3store.normalize_brand_key(Path(safe).name if "/" not in safe else safe)
    try:
        return RedirectResponse(url=s3store.public_object_url(storage_key), status_code=302)
    except s3store.SupabaseStorageError as e:
        raise HTTPException(status_code=500, detail=str(e))


@admin_router.get("/brand")
async def admin_get_brand(
    current_user: UserResponse = Depends(require_permission("manage_brand_settings")),
    db: AsyncSession = Depends(get_db),
):
    await ensure_schema()
    return await get_brand_settings(db)


@admin_router.put("/brand")
async def admin_put_brand(
    payload: SettingsPayload,
    request: Request,
    current_user: UserResponse = Depends(require_permission("manage_brand_settings")),
    db: AsyncSession = Depends(get_db),
):
    await ensure_schema()
    old = await get_brand_settings(db)
    new_val, old_json = await save_setting(db, KEY_BRAND, payload.settings, _actor(current_user))
    await log_action(
        db,
        "update_brand_settings",
        current_user.email,
        details=f"old={old_json}\nnew={payload.settings}",
        ip_address=request.client.host if request.client else None,
    )
    return {"success": True, "settings": new_val, "previous": old}


@admin_router.post("/brand/reset")
async def admin_reset_brand(
    request: Request,
    current_user: UserResponse = Depends(require_permission("manage_brand_settings")),
    db: AsyncSession = Depends(get_db),
):
    await ensure_schema()
    old = await get_brand_settings(db)
    new_val, old_json = await save_setting(db, KEY_BRAND, DEFAULT_BRAND, _actor(current_user))
    await log_action(
        db,
        "reset_brand_settings",
        current_user.email,
        details=f"old={old_json}",
        ip_address=request.client.host if request.client else None,
    )
    return {"success": True, "settings": new_val, "previous": old}


@admin_router.get("/registration-form")
async def admin_get_form(
    current_user: UserResponse = Depends(require_permission("manage_registration_form_settings")),
    db: AsyncSession = Depends(get_db),
):
    await ensure_schema()
    return await get_registration_form_settings(db)


@admin_router.put("/registration-form")
async def admin_put_form(
    payload: SettingsPayload,
    request: Request,
    current_user: UserResponse = Depends(require_permission("manage_registration_form_settings")),
    db: AsyncSession = Depends(get_db),
):
    await ensure_schema()
    old = await get_registration_form_settings(db)
    new_val, old_json = await save_setting(db, KEY_REG_FORM, payload.settings, _actor(current_user))
    await log_action(
        db,
        "update_registration_form_settings",
        current_user.email,
        details=f"old={old_json}\nnew={payload.settings}",
        ip_address=request.client.host if request.client else None,
    )
    return {"success": True, "settings": new_val, "previous": old}


@admin_router.post("/registration-form/reset")
async def admin_reset_form(
    request: Request,
    current_user: UserResponse = Depends(require_permission("manage_registration_form_settings")),
    db: AsyncSession = Depends(get_db),
):
    await ensure_schema()
    old = await get_registration_form_settings(db)
    new_val, old_json = await save_setting(db, KEY_REG_FORM, DEFAULT_REG_FORM, _actor(current_user))
    await log_action(
        db,
        "reset_registration_form_settings",
        current_user.email,
        details=f"old={old_json}",
        ip_address=request.client.host if request.client else None,
    )
    return {"success": True, "settings": new_val, "previous": old}


@admin_router.post("/upload-brand-asset")
async def upload_brand_asset(
    file: UploadFile = File(...),
    current_user: UserResponse = Depends(require_permission("manage_brand_settings")),
):
    ext = Path(file.filename or "logo.png").suffix.lower() or ".png"
    if ext not in {".png", ".jpg", ".jpeg", ".svg", ".webp", ".ico"}:
        raise HTTPException(status_code=400, detail="صيغة الملف غير مدعومة")
    name = f"{uuid.uuid4().hex}{ext}"
    storage_key = s3store.normalize_brand_key(name)
    content = await file.read()
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="الحد الأقصى 5MB")
    try:
        await s3store.upload_bytes(
            storage_key,
            content,
            content_type=file.content_type,
            upsert=True,
        )
    except s3store.SupabaseStorageError as e:
        logger.error("Brand upload to Supabase failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
    # Keep same API URL shape so existing brand settings continue to work
    url = f"/api/v1/public/app-settings/brand-file/{name}"
    return {"success": True, "url": url, "uploaded_by": _actor(current_user)}
