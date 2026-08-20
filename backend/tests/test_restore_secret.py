"""Restore confirmation secret: must be configured; no hardcoded RESTORE fallback."""
import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from core.database import Base
from models.app_settings import AppSetting  # noqa: F401 — register table
from services.restore_secret import (
    restore_secret_status,
    set_restore_secret,
    verify_restore_confirmation,
)


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_unconfigured_blocks_restore_including_restore_literal(db):
    status = await restore_secret_status(db)
    assert status["configured"] is False
    assert status["legacy_fallback_enabled"] is False
    with pytest.raises(HTTPException) as exc:
        await verify_restore_confirmation(db, "RESTORE")
    assert exc.value.status_code == 400
    assert "لم يُضبط" in str(exc.value.detail)
    with pytest.raises(HTTPException):
        await verify_restore_confirmation(db, "anything")


@pytest.mark.asyncio
async def test_configured_secret_verifies_and_never_returns_plaintext(db):
    result = await set_restore_secret(db, new_secret="Secret99", actor="admin")
    assert result["configured"] is True
    status = await restore_secret_status(db)
    assert status["configured"] is True
    assert "hash" not in status and "secret" not in status
    assert "Secret99" not in str(status)
    await verify_restore_confirmation(db, "Secret99")
    with pytest.raises(HTTPException):
        await verify_restore_confirmation(db, "RESTORE")
    with pytest.raises(HTTPException):
        await verify_restore_confirmation(db, "wrong")
