"""Admin panel users management - create/edit/delete/activate with permissions."""
import logging
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from dependencies.permissions import require_permission
from schemas.auth import UserResponse
from models.panel_users import PanelUser
from services.panel_auth import (
    ensure_schema,
    hash_password,
    normalize_permissions,
    permissions_to_json,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/admin/users", tags=["admin-users"])


class PermissionsModel(BaseModel):
    view: bool = False
    add: bool = False
    edit: bool = False
    delete: bool = False
    export: bool = False
    manage_users: bool = False
    manage_brand_settings: bool = False
    manage_registration_form_settings: bool = False


class PanelUserCreate(BaseModel):
    username: str = Field(..., min_length=2, max_length=100)
    password: str = Field(..., min_length=4, max_length=200)
    permissions: PermissionsModel = Field(default_factory=PermissionsModel)
    is_active: bool = True


class PanelUserUpdate(BaseModel):
    username: Optional[str] = Field(None, min_length=2, max_length=100)
    password: Optional[str] = Field(None, min_length=4, max_length=200)
    permissions: Optional[PermissionsModel] = None
    is_active: Optional[bool] = None


class PanelUserResponse(BaseModel):
    id: int
    username: str
    permissions: PermissionsModel
    is_active: bool
    is_super_admin: bool = False
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
        permissions=PermissionsModel(**perms),
        is_active=bool(user.is_active),
        is_super_admin=bool(getattr(user, "is_super_admin", False)),
        created_at=str(user.created_at) if user.created_at else None,
        updated_at=str(user.updated_at) if user.updated_at else None,
    )


@router.get("", response_model=PanelUserListResponse)
async def list_users(
    current_user: UserResponse = Depends(require_permission("manage_users")),
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
    current_user: UserResponse = Depends(require_permission("manage_users")),
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

        user = PanelUser(
            username=username,
            password_hash=hash_password(data.password),
            permissions=permissions_to_json(data.permissions.model_dump()),
            is_active=data.is_active,
            is_super_admin=False,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        db.add(user)
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
    current_user: UserResponse = Depends(require_permission("manage_users")),
    db: AsyncSession = Depends(get_db),
):
    await ensure_schema()

    try:
        result = await db.execute(select(PanelUser).where(PanelUser.id == user_id))
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=404, detail="المستخدم غير موجود")

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
            user.permissions = permissions_to_json(data.permissions.model_dump())

        if data.is_active is not None:
            user.is_active = data.is_active

        user.updated_at = datetime.now()
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
    current_user: UserResponse = Depends(require_permission("manage_users")),
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
        await db.commit()
        await db.refresh(user)
        return serialize_user(user)
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error toggling panel user: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="خطأ في تغيير حالة المستخدم")


@router.delete("/{user_id}")
async def delete_user(
    user_id: int,
    current_user: UserResponse = Depends(require_permission("manage_users")),
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

        await db.delete(user)
        await db.commit()
        return {"message": "تم حذف المستخدم بنجاح", "id": user_id}
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error deleting panel user: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="خطأ في حذف المستخدم")
