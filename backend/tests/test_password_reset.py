"""Password reset: OTP disabled; status + emergency super-admin still available."""
from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from core.database import Base, get_db
from models.panel_users import PanelUser
from models.password_reset import PasswordResetOtp  # noqa: F401
from routers.auth import router as auth_router
from services.membership_numbers import SystemCounter  # noqa: F401
from services.panel_auth import hash_password, verify_password


@pytest.mark.asyncio
async def test_otp_endpoints_disabled(tmp_path: Path):
    database_path = tmp_path / "pwd_reset.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path}")
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async def isolated_db_session():
        async with session_maker() as session:
            yield session

    app = FastAPI()
    app.include_router(auth_router)
    app.dependency_overrides[get_db] = isolated_db_session

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        st = await client.get("/api/v1/auth/password-reset/status")
        assert st.status_code == 200
        body = st.json()
        assert body["otp_enabled"] is False
        assert body["backup_codes_enabled"] is True
        assert body["email_delivery_available"] is False

        req = await client.post(
            "/api/v1/auth/password-reset/request",
            json={"username": "anyone", "channel": "email"},
        )
        assert req.status_code == 410

        conf = await client.post(
            "/api/v1/auth/password-reset/confirm",
            json={"username": "anyone", "otp": "123456", "new_password": "abcdef"},
        )
        assert conf.status_code == 410

    await engine.dispose()


@pytest.mark.asyncio
async def test_super_admin_emergency_reset(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SUPER_ADMIN_RECOVERY_SECRET", "ops-recovery-secret-xyz")
    database_path = tmp_path / "sa_reset.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path}")
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async with session_maker() as session:
        session.add(PanelUser(
            username="rootadmin",
            password_hash=hash_password("old-root-pass"),
            permissions="{}",
            is_active=True,
            is_super_admin=True,
        ))
        await session.commit()

    async def isolated_db_session():
        async with session_maker() as session:
            yield session

    app = FastAPI()
    app.include_router(auth_router)
    app.dependency_overrides[get_db] = isolated_db_session

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        bad = await client.post(
            "/api/v1/auth/password-reset/super-admin",
            json={"recovery_secret": "wrong-secret-xx", "new_password": "brand-new-root"},
        )
        assert bad.status_code == 403

        ok = await client.post(
            "/api/v1/auth/password-reset/super-admin",
            json={"recovery_secret": "ops-recovery-secret-xyz", "new_password": "brand-new-root"},
        )
        assert ok.status_code == 200

    async with session_maker() as session:
        from sqlalchemy import select

        user = (await session.execute(select(PanelUser).where(PanelUser.username == "rootadmin"))).scalar_one()
        assert verify_password("brand-new-root", user.password_hash)

    await engine.dispose()
