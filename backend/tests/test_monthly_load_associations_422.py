"""Regression: Production 422 when loading monthly associations.

Root cause on Production (main @ 3d5e8ab):
  Frontend called GET /api/v1/admin/financial/statements/grid?...
  financial.py registers GET /statements/{member_id} first (alphabetically
  before financial_erp), so FastAPI bound path member_id=\"grid\" → 422:
  Input should be a valid integer, unable to parse string as an integer
"""
from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from core.database import Base, get_db
from dependencies.auth import get_current_user
from models.panel_users import PanelUser  # noqa: F401
from models.registrations import Registrations
from routers.financial import router as financial_router
from routers.financial_erp import router as financial_erp_router
from schemas.auth import UserResponse


@pytest.mark.asyncio
async def test_load_all_associations_august_2026_no_422(tmp_path: Path):
    database_path = tmp_path / "monthly-load-422.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path}")
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async def isolated_db_session():
        async with session_maker() as session:
            yield session

    async def admin_user():
        return UserResponse(
            id="monthly-422-admin",
            email="monthly422@example.com",
            name="مختبر التحميل",
            role="admin",
            is_super_admin=True,
            permissions={},
        )

    # Same registration order as Production auto-import (financial before financial_erp).
    app = FastAPI()
    app.include_router(financial_router)
    app.include_router(financial_erp_router)
    app.dependency_overrides[get_db] = isolated_db_session
    app.dependency_overrides[get_current_user] = admin_user

    year, month = 2026, 8

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        services = await client.get("/api/v1/admin/financial/service-types?ensure_canonical=true")
        assert services.status_code == 200
        shipping = next(x for x in services.json()["items"] if x["code"] == "shipping")

        company = await client.post("/api/v1/admin/financial/companies", json={
            "name": "شركة تحميل الارتباطات",
            "service_type_id": shipping["id"],
            "owner_name": "مالك",
            "address": "بغداد",
            "mobile": "07709998877",
            "cooperation_started_at": "2026-01-01",
            "cooperation_status": "active",
            "status": "active",
        })
        assert company.status_code == 200, company.text
        company_id = company.json()["id"]

        carton = await client.post(f"/api/v1/admin/financial/companies/{company_id}/pricing-items", json={
            "name": "كارتون", "unit": "كارتون", "company_unit_price": 30000,
            "mfec_share_type": "fixed", "mfec_share_value": 3000, "effective_from": "2026-01-01",
        })
        kilo = await client.post(f"/api/v1/admin/financial/companies/{company_id}/pricing-items", json={
            "name": "كيلو", "unit": "كيلو", "company_unit_price": 1000,
            "mfec_share_type": "percentage", "mfec_share_value": 10, "effective_from": "2026-01-01",
        })
        assert carton.status_code == 200 and kilo.status_code == 200
        carton_id, kilo_id = carton.json()["id"], kilo.json()["id"]

        async with session_maker() as session:
            member = Registrations(
                business_name="متجر أحمد", merchant_name="أحمد", phone="07801112233",
                governorate="بغداد", area="الكرادة", business_type="تجارة", image_key="t",
                status="approved", membership_number="MF-LOAD-1", membership_status="active",
                user_id="load-422",
            )
            session.add(member)
            await session.commit()
            member_id = member.id

        account = await client.post("/api/v1/admin/financial/member-accounts", json={
            "member_id": member_id,
            "company_id": company_id,
            "registered_name": "أحمد",
            "started_at": "2026-01-01",
            "status": "active",
            "is_active": True,
            "items": [
                {"pricing_item_id": carton_id, "is_active": True},
                {"pricing_item_id": kilo_id, "is_active": True},
            ],
        })
        assert account.status_code == 200, account.text

        # --- BEFORE (Production bug): path segment "grid" parsed as member_id ---
        before_url = (
            f"/api/v1/admin/financial/statements/grid"
            f"?company_id={company_id}&accounting_year={year}&accounting_month={month}"
        )
        before = await client.get(before_url)
        assert before.status_code == 422, before.text
        detail = before.json()["detail"]
        assert isinstance(detail, list)
        assert detail[0]["loc"] == ["path", "member_id"]
        assert detail[0]["input"] == "grid"
        assert "valid integer" in detail[0]["msg"]

        # --- AFTER: fixed path; "كل الأعضاء / كل الفقرات / كل المحافظات" = omit params ---
        after_url = (
            f"/api/v1/admin/financial/monthly-statements/grid"
            f"?company_id={company_id}&accounting_year={year}&accounting_month={month}"
        )
        # Period 01/08/2026–30/08/2026 is implied by year=2026&month=8 (no empty filter strings).
        after = await client.get(after_url)
        assert after.status_code == 200, after.text
        body = after.json()
        assert body["period_start"] == "2026-08-01"
        assert body["period_end"] == "2026-08-31"
        assert body["row_count"] == 2
        assert len(body["items"]) == 2
        assert {r["pricing_item_name"] for r in body["items"]} == {"كارتون", "كيلو"}

        # Empty-string filters must not be used; if sent they remain 422 (do not hide bad IDs).
        bad_empty = await client.get(
            f"{after_url}&member_id=&pricing_item_id="
        )
        assert bad_empty.status_code == 422, bad_empty.text

        # Specific member + specific pricing item (integers only) → 200, one row.
        filtered = await client.get(
            f"/api/v1/admin/financial/monthly-statements/grid"
            f"?company_id={company_id}&accounting_year={year}&accounting_month={month}"
            f"&member_id={member_id}&pricing_item_id={carton_id}"
        )
        assert filtered.status_code == 200, filtered.text
        assert filtered.json()["row_count"] == 1
        assert filtered.json()["items"][0]["pricing_item_name"] == "كارتون"
        assert filtered.json()["items"][0]["member_id"] == member_id

        print(
            "LOAD_ASSOC_REGRESSION "
            f"before_status={before.status_code} before_input={detail[0]['input']} "
            f"after_status={after.status_code} after_rows={body['row_count']} "
            f"filtered_status={filtered.status_code} filtered_rows={filtered.json()['row_count']}"
        )

    await engine.dispose()
