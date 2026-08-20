"""Backup codes + OTP disabled + admin set-password."""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from core.database import Base, get_db
from dependencies.auth import get_current_user
from models.backup_codes import PanelUserBackupCode  # noqa: F401
from models.financial import FinancialAuditLog  # noqa: F401
from models.panel_users import PanelUser
from models.registrations import Registrations  # noqa: F401
from routers.admin_users import router as admin_users_router
from routers.auth import router as auth_router
from schemas.auth import UserResponse
from services.panel_auth import PERMISSION_KEYS, hash_password, permissions_to_json, verify_password


@pytest.mark.asyncio
async def test_backup_codes_flow_and_otp_disabled(tmp_path: Path):
    database_path = tmp_path / "backup_codes.db"
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
            name="superadmin",
            role="admin",
            is_super_admin=True,
            permissions={k: True for k in PERMISSION_KEYS},
        )

    app = FastAPI()
    app.include_router(auth_router)
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
        clerk = PanelUser(
            username="clerk1",
            password_hash=hash_password("old-pass-99"),
            permissions=permissions_to_json({"view": True}),
            is_active=True,
            is_super_admin=False,
        )
        session.add(clerk)
        await session.commit()
        await session.refresh(clerk)
        clerk_id = clerk.id

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        st = await client.get("/api/v1/auth/password-reset/status")
        assert st.status_code == 200
        assert st.json()["otp_enabled"] is False
        assert st.json()["backup_codes_enabled"] is True

        blocked = await client.post(
            "/api/v1/auth/password-reset/request",
            json={"username": "clerk1", "channel": "email"},
        )
        assert blocked.status_code == 410

        gen = await client.post(f"/api/v1/admin/users/{clerk_id}/backup-codes")
        assert gen.status_code == 200, gen.text
        codes = gen.json()["codes"]
        assert len(codes) == 5
        code = codes[0]

        status = await client.get(f"/api/v1/admin/users/{clerk_id}/backup-codes/status")
        assert status.json()["remaining"] == 5

        reset = await client.post(
            "/api/v1/auth/password-reset/backup-code",
            json={"username": "clerk1", "code": code, "new_password": "new-pass-42"},
        )
        assert reset.status_code == 200, reset.text

        # code one-time
        again = await client.post(
            "/api/v1/auth/password-reset/backup-code",
            json={"username": "clerk1", "code": code, "new_password": "another-99"},
        )
        assert again.status_code == 400

        async with session_maker() as session:
            from sqlalchemy import select

            row = (await session.execute(select(PanelUser).where(PanelUser.id == clerk_id))).scalar_one()
            assert verify_password("new-pass-42", row.password_hash)

        # admin set password
        setp = await client.post(
            f"/api/v1/admin/users/{clerk_id}/set-password",
            json={"new_password": "admin-set-77"},
        )
        assert setp.status_code == 200
        async with session_maker() as session:
            from sqlalchemy import select

            row = (await session.execute(select(PanelUser).where(PanelUser.id == clerk_id))).scalar_one()
            assert verify_password("admin-set-77", row.password_hash)

    await engine.dispose()
