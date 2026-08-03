"""Permission helpers for local panel users."""
from typing import Callable, Dict, Optional

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from dependencies.auth import get_current_user
from models.panel_users import PanelUser
from schemas.auth import UserResponse
from services.panel_auth import PERMISSION_KEYS, default_permissions, normalize_permissions

PERM_DENIED = "ليس لديك صلاحية لتنفيذ هذا الإجراء."


def permissions_from_user_payload(payload_perms) -> Dict[str, bool]:
    return normalize_permissions(payload_perms)


async def load_user_permissions(db: AsyncSession, user: UserResponse) -> Dict[str, bool]:
    """Load live permissions from DB for panel users; super admin = all true."""
    if getattr(user, "is_super_admin", False):
        return default_permissions(all_true=True)

    # panel:{id}
    panel_id = None
    if user.id and str(user.id).startswith("panel:"):
        try:
            panel_id = int(str(user.id).split(":", 1)[1])
        except ValueError:
            panel_id = None

    if panel_id is not None:
        result = await db.execute(select(PanelUser).where(PanelUser.id == panel_id))
        panel = result.scalar_one_or_none()
        if panel:
            if getattr(panel, "is_super_admin", False):
                return default_permissions(all_true=True)
            return normalize_permissions(panel.permissions)

    # JWT-embedded permissions fallback (never grant all just because role=admin)
    if getattr(user, "permissions", None):
        return normalize_permissions(user.permissions)

    return default_permissions(False)


def require_permission(permission: str) -> Callable:
    """FastAPI dependency factory: enforce a single permission key."""

    async def _checker(
        current_user: UserResponse = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> UserResponse:
        if current_user.role != "admin":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=PERM_DENIED)

        perms = await load_user_permissions(db, current_user)
        current_user.permissions = perms  # type: ignore[attr-defined]
        if getattr(current_user, "is_super_admin", False) or perms.get(permission, False):
            return current_user

        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=PERM_DENIED)

    return _checker


def require_any_permission(*permissions: str) -> Callable:
    async def _checker(
        current_user: UserResponse = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> UserResponse:
        if current_user.role != "admin":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=PERM_DENIED)
        perms = await load_user_permissions(db, current_user)
        current_user.permissions = perms  # type: ignore[attr-defined]
        if getattr(current_user, "is_super_admin", False):
            return current_user
        if any(perms.get(p, False) for p in permissions):
            return current_user
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=PERM_DENIED)

    return _checker
