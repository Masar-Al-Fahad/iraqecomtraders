"""Resolve the acting panel user's display name from the database (never trust client)."""
from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.panel_users import PanelUser
from schemas.auth import UserResponse


def actor_from_user(current_user: UserResponse) -> str:
    """Fallback from JWT claims only."""
    if current_user.name and str(current_user.name).strip():
        return str(current_user.name).strip()
    email = (current_user.email or "").strip()
    if email.endswith("@local"):
        return email[: -len("@local")] or "User"
    if email:
        return email
    return "User"


async def resolve_actor_name(db: AsyncSession, current_user: UserResponse) -> str:
    """Prefer live PanelUser.username from DB so last_modified_by is always correct."""
    uid = str(getattr(current_user, "id", "") or "")
    if uid.startswith("panel:"):
        try:
            panel_id = int(uid.split(":", 1)[1])
        except ValueError:
            panel_id = None
        if panel_id is not None:
            result = await db.execute(select(PanelUser).where(PanelUser.id == panel_id))
            panel: Optional[PanelUser] = result.scalar_one_or_none()
            if panel and panel.username and str(panel.username).strip():
                return str(panel.username).strip()
    return actor_from_user(current_user)
