"""Forgot-password OTP flow: no enumeration, one-time OTP, rate limits."""
import os
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
from services.panel_auth import hash_password
from services.password_reset import peek_dev_otp


@pytest.mark.asyncio
async def test_password_reset_otp_happy_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("PASSWORD_RESET_DEV_ECHO", "true")
    monkeypatch.setenv("ENVIRONMENT", "dev")
    database_path = tmp_path / "pwd_reset.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path}")
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async with session_maker() as session:
        session.add(PanelUser(
            username="clerk1",
            password_hash=hash_password("old-pass-123"),
            permissions="{}",
            is_active=True,
            is_super_admin=False,
            email="clerk1@example.com",
            phone="07701234567",
            recovery_preferred="email",
        ))
        await session.commit()

    async def isolated_db_session():
        async with session_maker() as session:
            yield session

    app = FastAPI()
    app.include_router(auth_router)
    app.dependency_overrides[get_db] = isolated_db_session

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        unknown = await client.post("/api/v1/auth/password-reset/request", json={"username": "nope"})
        assert unknown.status_code == 200
        assert "إن وُجد" in unknown.json()["message"]
        assert "dev_otp" not in unknown.json()

        req = await client.post("/api/v1/auth/password-reset/request", json={
            "username": "clerk1", "channel": "email",
        })
        assert req.status_code == 200, req.text
        body = req.json()
        assert body["ok"] is True
        otp = body.get("dev_otp") or peek_dev_otp("clerk1")
        assert otp and len(otp) == 6

        bad = await client.post("/api/v1/auth/password-reset/confirm", json={
            "username": "clerk1", "otp": "000000", "new_password": "new-pass-456",
        })
        assert bad.status_code == 400

        ok = await client.post("/api/v1/auth/password-reset/confirm", json={
            "username": "clerk1", "otp": otp, "new_password": "new-pass-456",
        })
        assert ok.status_code == 200, ok.text

        reuse = await client.post("/api/v1/auth/password-reset/confirm", json={
            "username": "clerk1", "otp": otp, "new_password": "another-pass",
        })
        assert reuse.status_code == 400

        login_old = await client.post("/api/v1/auth/login", json={
            "username": "clerk1", "password": "old-pass-123",
        })
        assert login_old.status_code == 401

        login_new = await client.post("/api/v1/auth/login", json={
            "username": "clerk1", "password": "new-pass-456",
        })
        assert login_new.status_code == 200, login_new.text
        assert login_new.json()["token"]

    await engine.dispose()


@pytest.mark.asyncio
async def test_password_reset_status_endpoint(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("SMTP_HOST", raising=False)
    monkeypatch.delenv("SMTP_FROM", raising=False)
    monkeypatch.delenv("SMS_WEBHOOK_URL", raising=False)
    monkeypatch.delenv("PASSWORD_RESET_DEV_ECHO", raising=False)
    database_path = tmp_path / "pwd_status.db"
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
        assert body["email_delivery_available"] is False
        assert body["sms_delivery_available"] is False
        assert body["dev_echo_enabled"] is False

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
            username="admin",
            password_hash=hash_password("old-admin"),
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
        denied = await client.post("/api/v1/auth/password-reset/super-admin", json={
            "recovery_secret": "wrong-secret-value", "new_password": "brand-new-admin",
        })
        assert denied.status_code == 403

        ok = await client.post("/api/v1/auth/password-reset/super-admin", json={
            "recovery_secret": "ops-recovery-secret-xyz",
            "new_password": "brand-new-admin",
        })
        assert ok.status_code == 200, ok.text

        login = await client.post("/api/v1/auth/login", json={
            "username": "admin", "password": "brand-new-admin",
        })
        assert login.status_code == 200

    await engine.dispose()
