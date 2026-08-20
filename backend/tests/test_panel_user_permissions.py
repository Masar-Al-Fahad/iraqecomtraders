"""Panel user permissions must persist financial.* and backups.* keys."""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from core.database import Base, get_db
from dependencies.auth import get_current_user
from models.financial import FinancialAuditLog  # noqa: F401
from models.panel_users import PanelUser
from models.registrations import Registrations  # noqa: F401
from routers.admin_users import router as admin_users_router
from schemas.auth import UserResponse
from services.panel_auth import PERMISSION_KEYS, hash_password, normalize_permissions, permissions_to_json


@pytest.mark.asyncio
async def test_panel_user_financial_permissions_persist_create_update_reload(tmp_path: Path):
    database_path = tmp_path / "panel_perms.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path}")
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async def isolated_db_session():
        async with session_maker() as session:
            yield session

    async def admin_user():
        return UserResponse(
            id="panel:1",
            email="super@example.com",
            name="Super Admin",
            role="admin",
            is_super_admin=True,
            permissions={k: True for k in PERMISSION_KEYS},
        )

    app = FastAPI()
    app.include_router(admin_users_router)
    app.dependency_overrides[get_db] = isolated_db_session
    app.dependency_overrides[get_current_user] = admin_user

    async with session_maker() as session:
        session.add(
            PanelUser(
                username="superadmin",
                password_hash=hash_password("secret123"),
                permissions=permissions_to_json({k: True for k in PERMISSION_KEYS}),
                is_active=True,
                is_super_admin=True,
            )
        )
        await session.commit()

    sample_perms = {k: False for k in PERMISSION_KEYS}
    sample_perms.update(
        {
            "view": True,
            "manage_users": True,
            "financial.dashboard.view": True,
            "financial.expenses.view": True,
            "financial.expenses.create": True,
            "financial.revenues.view": True,
            "backups.view": True,
            "backups.restore": True,
        }
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        created = await client.post(
            "/api/v1/admin/users",
            json={
                "username": "finance_clerk",
                "password": "clerk-pass-1",
                "permissions": sample_perms,
                "is_active": True,
            },
        )
        assert created.status_code == 200, created.text
        body = created.json()
        user_id = body["id"]
        perms = body["permissions"]
        assert perms["financial.dashboard.view"] is True
        assert perms["financial.expenses.create"] is True
        assert perms["backups.restore"] is True
        assert perms["financial.companies.delete"] is False

        listed = await client.get("/api/v1/admin/users")
        assert listed.status_code == 200
        item = next(x for x in listed.json()["items"] if x["id"] == user_id)
        assert item["permissions"]["financial.expenses.view"] is True
        assert item["permissions"]["backups.view"] is True

        updated_perms = dict(item["permissions"])
        updated_perms["financial.expenses.create"] = False
        updated_perms["financial.reports.xlsx"] = True
        updated = await client.put(
            f"/api/v1/admin/users/{user_id}",
            json={"permissions": updated_perms},
        )
        assert updated.status_code == 200, updated.text
        up = updated.json()["permissions"]
        assert up["financial.expenses.create"] is False
        assert up["financial.reports.xlsx"] is True
        assert up["backups.restore"] is True

        listed2 = await client.get("/api/v1/admin/users")
        item2 = next(x for x in listed2.json()["items"] if x["id"] == user_id)
        assert item2["permissions"]["financial.expenses.create"] is False
        assert item2["permissions"]["financial.reports.xlsx"] is True
        assert item2["permissions"]["financial.dashboard.view"] is True
        assert item2["permissions"]["backups.restore"] is True

        async with session_maker() as session:
            row = (await session.execute(select(PanelUser).where(PanelUser.id == user_id))).scalar_one()
            stored = normalize_permissions(row.permissions)
            assert stored["financial.reports.xlsx"] is True
            assert stored["backups.view"] is True

    await engine.dispose()
