"""Voucher numbering for REC-/PAY- receipts and payments (4-digit padded)."""
from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from core.database import Base, get_db
from dependencies.auth import get_current_user
from models.panel_users import PanelUser  # noqa: F401
from models.registrations import Registrations  # noqa: F401
from routers.financial import router as financial_router
from routers.financial_erp import router as financial_erp_router
from schemas.auth import UserResponse
from services.membership_numbers import SystemCounter  # noqa: F401


@pytest.mark.asyncio
async def test_rec_pay_numbering_preview_save_cancel_independent(tmp_path: Path):
    database_path = tmp_path / "vouchers.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path}")
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async def isolated_db_session():
        async with session_maker() as session:
            yield session

    async def admin_user():
        return UserResponse(
            id="voucher-admin",
            email="voucher@example.com",
            name="مختبر الوصولات",
            role="admin",
            is_super_admin=True,
            permissions={},
        )

    app = FastAPI()
    app.include_router(financial_router)
    app.include_router(financial_erp_router)
    app.dependency_overrides[get_db] = isolated_db_session
    app.dependency_overrides[get_current_user] = admin_user

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        services = await client.get("/api/v1/admin/financial/service-types?ensure_canonical=true")
        shipping = next(x for x in services.json()["items"] if x["code"] == "shipping")
        company = await client.post("/api/v1/admin/financial/companies", json={
            "name": "شركة وصولات",
            "service_type_id": shipping["id"],
            "owner_name": "مالك",
            "address": "بغداد",
            "mobile": "07701110000",
            "cooperation_started_at": "2026-01-01",
            "cooperation_status": "active",
            "status": "active",
        })
        assert company.status_code == 200, company.text
        company_id = company.json()["id"]

        # Set next REC = 5 and PAY = 5 → REC-0005 / PAY-0005
        set_nums = await client.put("/api/v1/admin/financial/voucher-numbers", json={
            "next_rec": 5, "next_pay": 5,
        })
        assert set_nums.status_code == 200, set_nums.text
        assert set_nums.json()["preview_rec"] == "REC-0005"
        assert set_nums.json()["preview_pay"] == "PAY-0005"

        # Preview / peek does not consume
        peek1 = await client.get("/api/v1/admin/financial/voucher-numbers")
        peek2 = await client.get("/api/v1/admin/financial/voucher-numbers")
        assert peek1.status_code == 200 and peek2.status_code == 200
        assert peek1.json()["preview_rec"] == "REC-0005"
        assert peek2.json()["preview_rec"] == "REC-0005"
        assert peek1.json()["preview_pay"] == "PAY-0005"
        assert peek2.json()["preview_pay"] == "PAY-0005"

        # Save two receipts
        r1 = await client.post("/api/v1/admin/financial/revenues", json={
            "company_id": company_id,
            "received_at": "2026-08-01",
            "amount": 100000,
            "receipt_method": "تحويل",
            "category": "خدمة",
            "description": "قبض أول",
        })
        r2 = await client.post("/api/v1/admin/financial/revenues", json={
            "company_id": company_id,
            "received_at": "2026-08-02",
            "amount": 200000,
            "receipt_method": "نقدًا",
            "category": "خدمة",
            "description": "قبض ثانٍ",
        })
        assert r1.status_code == 200, r1.text
        assert r2.status_code == 200, r2.text
        assert r1.json()["receipt_number"] == "REC-0005"
        assert r2.json()["receipt_number"] == "REC-0006"

        after_rec = await client.get("/api/v1/admin/financial/voucher-numbers")
        assert after_rec.json()["preview_rec"] == "REC-0007"

        # Save two payments — independent sequence + new expense fields
        p1 = await client.post("/api/v1/admin/financial/expenses", json={
            "expense_date": "2026-08-03",
            "accounting_year": 2026,
            "accounting_month": 8,
            "payee": "مورد أ",
            "person_name": "أحمد",
            "company_name": "شركة المورد",
            "payment_method": "تحويل",
            "category": "تشغيل",
            "description": "صرف أول",
            "amount": 50000,
        })
        p2 = await client.post("/api/v1/admin/financial/expenses", json={
            "expense_date": "2026-08-04",
            "accounting_year": 2026,
            "accounting_month": 8,
            "payee": "مورد ب",
            "person_name": "سارة",
            "company_name": None,
            "payment_method": "نقدًا",
            "category": "تشغيل",
            "description": "صرف ثانٍ",
            "amount": 75000,
        })
        assert p1.status_code == 200, p1.text
        assert p2.status_code == 200, p2.text
        assert p1.json()["payment_number"] == "PAY-0005"
        assert p2.json()["payment_number"] == "PAY-0006"

        after_pay = await client.get("/api/v1/admin/financial/voucher-numbers")
        assert after_pay.json()["preview_pay"] == "PAY-0007"
        assert after_pay.json()["preview_rec"] == "REC-0007"

        expenses = await client.get("/api/v1/admin/financial/expenses?include_deleted=true")
        assert expenses.status_code == 200
        pay_row = next(x for x in expenses.json()["items"] if x["payment_number"] == "PAY-0005")
        assert pay_row["person_name"] == "أحمد"
        assert pay_row["company_name"] == "شركة المورد"
        assert pay_row["payee"] == "مورد أ"

        # Duplicate next number blocked
        clash = await client.put("/api/v1/admin/financial/voucher-numbers", json={"next_rec": 5})
        assert clash.status_code == 409, clash.text

        # Cancel does not free number
        cancel = await client.delete(f"/api/v1/admin/financial/revenues/{r1.json()['id']}")
        assert cancel.status_code == 200
        assert cancel.json()["status"] == "cancelled"
        assert cancel.json()["receipt_number"] == "REC-0005"
        still_blocked = await client.put("/api/v1/admin/financial/voucher-numbers", json={"next_rec": 5})
        assert still_blocked.status_code == 409

        # Refresh / reopen lists keep numbers
        revenues = await client.get("/api/v1/admin/financial/revenues?include_deleted=true")
        assert revenues.status_code == 200
        rec_nums = {x["receipt_number"] for x in revenues.json()["items"]}
        pay_nums = {x["payment_number"] for x in expenses.json()["items"]}
        assert "REC-0005" in rec_nums and "REC-0006" in rec_nums
        assert "PAY-0005" in pay_nums and "PAY-0006" in pay_nums
        cancelled = next(x for x in revenues.json()["items"] if x["receipt_number"] == "REC-0005")
        assert cancelled["status"] == "cancelled"
        assert cancelled["deleted"] is True

    await engine.dispose()
