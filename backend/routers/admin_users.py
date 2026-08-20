"""Admin panel users management - create/edit/delete/activate with permissions."""
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from dependencies.permissions import require_any_permission
from schemas.auth import UserResponse
from models.panel_users import PanelUser
from services.panel_auth import (
    ensure_schema,
    hash_password,
    normalize_permissions,
    permissions_to_json,
)
from services.actor import resolve_actor_name
from services.financial import add_audit

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/admin/users", tags=["admin-users"])


def _coerce_permissions(raw: Any) -> Dict[str, bool]:
    """Accept full PERMISSION_KEYS map (legacy + financial.* + backups.*)."""
    if raw is None:
        return normalize_permissions({})
    if isinstance(raw, BaseModel):
        raw = raw.model_dump()
    if not isinstance(raw, dict):
        return normalize_permissions({})
    return normalize_permissions(raw)


class PanelUserCreate(BaseModel):
    username: str = Field(..., min_length=2, max_length=100)
    password: str = Field(..., min_length=4, max_length=200)
    permissions: Dict[str, bool] = Field(default_factory=dict)
    is_active: bool = True
    email: Optional[str] = Field(None, max_length=255)
    phone: Optional[str] = Field(None, max_length=40)
    recovery_preferred: Optional[str] = Field(None, max_length=20)


class PanelUserUpdate(BaseModel):
    username: Optional[str] = Field(None, min_length=2, max_length=100)
    password: Optional[str] = Field(None, min_length=4, max_length=200)
    permissions: Optional[Dict[str, bool]] = None
    is_active: Optional[bool] = None
    email: Optional[str] = Field(None, max_length=255)
    phone: Optional[str] = Field(None, max_length=40)
    recovery_preferred: Optional[str] = Field(None, max_length=20)


class PanelUserResponse(BaseModel):
    id: int
    username: str
    permissions: Dict[str, bool]
    is_active: bool
    is_super_admin: bool = False
    email: Optional[str] = None
    phone: Optional[str] = None
    recovery_preferred: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    class Config:
        from_attributes = True


class PanelUserListResponse(BaseModel):
    items: List[PanelUserResponse]
    total: int


def serialize_user(user: PanelUser) -> PanelUserResponse:
    perms = normalize_permissions(user.permissions)
    return PanelUserResponse(
        id=user.id,
        username=user.username,
        permissions=perms,
        is_active=bool(user.is_active),
        is_super_admin=bool(getattr(user, "is_super_admin", False)),
        email=getattr(user, "email", None),
        phone=getattr(user, "phone", None),
        recovery_preferred=getattr(user, "recovery_preferred", None),
        created_at=str(user.created_at) if user.created_at else None,
        updated_at=str(user.updated_at) if user.updated_at else None,
    )


@router.get("", response_model=PanelUserListResponse)
async def list_users(
    current_user: UserResponse = Depends(require_any_permission("manage_users", "manage_users_permissions")),
    db: AsyncSession = Depends(get_db),
):
    await ensure_schema()

    try:
        result = await db.execute(select(PanelUser).order_by(PanelUser.id.asc()))
        items = result.scalars().all()
        return PanelUserListResponse(
            items=[serialize_user(u) for u in items],
            total=len(items),
        )
    except Exception as e:
        logger.error(f"Error listing panel users: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="خطأ في جلب المستخدمين")


@router.post("", response_model=PanelUserResponse)
async def create_user(
    data: PanelUserCreate,
    current_user: UserResponse = Depends(require_any_permission("manage_users", "manage_users_permissions")),
    db: AsyncSession = Depends(get_db),
):
    await ensure_schema()

    username = data.username.strip()
    if not username:
        raise HTTPException(status_code=400, detail="اسم المستخدم مطلوب")

    try:
        existing = await db.execute(select(PanelUser).where(PanelUser.username == username))
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="اسم المستخدم موجود مسبقاً")

        perms = _coerce_permissions(data.permissions)
        user = PanelUser(
            username=username,
            password_hash=hash_password(data.password),
            permissions=permissions_to_json(perms),
            is_active=data.is_active,
            is_super_admin=False,
            email=(data.email or "").strip() or None,
            phone=(data.phone or "").strip() or None,
            recovery_preferred=(data.recovery_preferred or "").strip() or None,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        db.add(user)
        await db.flush()
        add_audit(
            db, action="create", entity_type="panel_user", entity_id=user.id,
            actor=await resolve_actor_name(db, current_user),
            new_values={"username": username, "permissions": perms, "is_active": data.is_active},
        )
        await db.commit()
        await db.refresh(user)
        return serialize_user(user)
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error creating panel user: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="خطأ في إنشاء المستخدم")


@router.put("/{user_id}", response_model=PanelUserResponse)
async def update_user(
    user_id: int,
    data: PanelUserUpdate,
    current_user: UserResponse = Depends(require_any_permission("manage_users", "manage_users_permissions")),
    db: AsyncSession = Depends(get_db),
):
    await ensure_schema()

    try:
        result = await db.execute(select(PanelUser).where(PanelUser.id == user_id))
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=404, detail="المستخدم غير موجود")

        old_values = {
            "username": user.username,
            "permissions": normalize_permissions(user.permissions),
            "is_active": bool(user.is_active),
        }
        if data.username is not None:
            new_username = data.username.strip()
            if not new_username:
                raise HTTPException(status_code=400, detail="اسم المستخدم مطلوب")
            dup = await db.execute(
                select(PanelUser).where(PanelUser.username == new_username, PanelUser.id != user_id)
            )
            if dup.scalar_one_or_none():
                raise HTTPException(status_code=400, detail="اسم المستخدم موجود مسبقاً")
            user.username = new_username

        if data.password is not None and data.password.strip():
            user.password_hash = hash_password(data.password)

        if data.permissions is not None:
            user.permissions = permissions_to_json(_coerce_permissions(data.permissions))

        if data.is_active is not None:
            user.is_active = data.is_active

        if data.email is not None:
            user.email = data.email.strip() or None
        if data.phone is not None:
            user.phone = data.phone.strip() or None
        if data.recovery_preferred is not None:
            user.recovery_preferred = data.recovery_preferred.strip() or None

        user.updated_at = datetime.now()
        add_audit(
            db, action="update", entity_type="panel_user", entity_id=user.id,
            actor=await resolve_actor_name(db, current_user), old_values=old_values,
            new_values={
                "username": user.username, "permissions": normalize_permissions(user.permissions),
                "is_active": bool(user.is_active), "password_reset": bool(data.password),
                "email": getattr(user, "email", None), "phone": getattr(user, "phone", None),
                "recovery_preferred": getattr(user, "recovery_preferred", None),
            },
        )
        await db.commit()
        await db.refresh(user)
        return serialize_user(user)
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error updating panel user: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="خطأ في تحديث المستخدم")


@router.patch("/{user_id}/toggle-active", response_model=PanelUserResponse)
async def toggle_user_active(
    user_id: int,
    current_user: UserResponse = Depends(require_any_permission("manage_users", "manage_users_permissions")),
    db: AsyncSession = Depends(get_db),
):
    await ensure_schema()

    try:
        result = await db.execute(select(PanelUser).where(PanelUser.id == user_id))
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=404, detail="المستخدم غير موجود")

        if getattr(user, "is_super_admin", False):
            raise HTTPException(status_code=400, detail="لا يمكن تعطيل حساب Super Admin")

        user.is_active = not bool(user.is_active)
        user.updated_at = datetime.now()
        add_audit(
            db, action="toggle_active", entity_type="panel_user", entity_id=user.id,
            actor=await resolve_actor_name(db, current_user),
            new_values={"is_active": bool(user.is_active)},
        )
        await db.commit()
        await db.refresh(user)
        return serialize_user(user)
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error toggling panel user: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="خطأ في تغيير حالة المستخدم")


@router.post("/{user_id}/backup-codes")
async def generate_user_backup_codes(
    user_id: int,
    current_user: UserResponse = Depends(require_any_permission("manage_users", "manage_users_permissions")),
    db: AsyncSession = Depends(get_db),
):
    """Generate 5 one-time backup codes (plaintext returned once). Revokes previous unused set."""
    await ensure_schema()
    from services.backup_codes import generate_backup_codes

    result = await db.execute(select(PanelUser).where(PanelUser.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="المستخدم غير موجود")
    return await generate_backup_codes(
        db, user=user, actor=await resolve_actor_name(db, current_user),
    )


@router.get("/{user_id}/backup-codes/status")
async def user_backup_codes_status(
    user_id: int,
    current_user: UserResponse = Depends(require_any_permission("manage_users", "manage_users_permissions")),
    db: AsyncSession = Depends(get_db),
):
    await ensure_schema()
    from services.backup_codes import backup_codes_status

    result = await db.execute(select(PanelUser).where(PanelUser.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="المستخدم غير موجود")
    return await backup_codes_status(db, user_id)


class SetPasswordIn(BaseModel):
    new_password: str = Field(..., min_length=6, max_length=200)


@router.post("/{user_id}/set-password")
async def set_user_password(
    user_id: int,
    data: SetPasswordIn,
    current_user: UserResponse = Depends(require_any_permission("manage_users", "manage_users_permissions")),
    db: AsyncSession = Depends(get_db),
):
    """Admin/super-admin sets another user's password (hashed; never logged)."""
    await ensure_schema()
    from services.backup_codes import admin_set_password

    result = await db.execute(select(PanelUser).where(PanelUser.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="المستخدم غير موجود")
    return await admin_set_password(
        db,
        user=user,
        new_password=data.new_password,
        actor=await resolve_actor_name(db, current_user),
    )


@router.delete("/{user_id}")
async def delete_user(
    user_id: int,
    current_user: UserResponse = Depends(require_any_permission("manage_users", "manage_users_permissions")),
    db: AsyncSession = Depends(get_db),
):
    await ensure_schema()

    try:
        result = await db.execute(select(PanelUser).where(PanelUser.id == user_id))
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=404, detail="المستخدم غير موجود")

        if getattr(user, "is_super_admin", False):
            raise HTTPException(status_code=400, detail="لا يمكن حذف حساب Super Admin")

        add_audit(
            db, action="delete", entity_type="panel_user", entity_id=user.id,
            actor=await resolve_actor_name(db, current_user),
            old_values={"username": user.username, "permissions": normalize_permissions(user.permissions)},
        )
        await db.delete(user)
        await db.commit()
        return {"message": "تم حذف المستخدم بنجاح", "id": user_id}
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error deleting panel user: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="خطأ في حذف المستخدم")
