"""Monthly entry page: one row per member pricing item, save, reopen, update."""
from decimal import Decimal
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
async def test_monthly_entry_one_member_two_items_save_refresh_update(tmp_path: Path):
    database_path = tmp_path / "monthly-entry.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path}")
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async def isolated_db_session():
        async with session_maker() as session:
            yield session

    async def admin_user():
        return UserResponse(
            id="monthly-admin",
            email="monthly@example.com",
            name="مختبر الإدخال",
            role="admin",
            is_super_admin=True,
            permissions={},
        )

    app = FastAPI()
    app.include_router(financial_router)
    app.include_router(financial_erp_router)
    app.dependency_overrides[get_db] = isolated_db_session
    app.dependency_overrides[get_current_user] = admin_user

    year, month = 2026, 8

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        services = await client.get("/api/v1/admin/financial/service-types?ensure_canonical=true")
        assert services.status_code == 200
        shipping = next(item for item in services.json()["items"] if item["code"] == "shipping")

        company = await client.post("/api/v1/admin/financial/companies", json={
            "name": "شركة إدخال شهري",
            "service_type_id": shipping["id"],
            "owner_name": "مالك",
            "address": "بغداد",
            "mobile": "07701234567",
            "cooperation_started_at": "2026-01-01",
            "cooperation_status": "active",
            "status": "active",
        })
        assert company.status_code == 200, company.text
        company_id = company.json()["id"]

        carton = await client.post(f"/api/v1/admin/financial/companies/{company_id}/pricing-items", json={
            "name": "كارتون",
            "unit": "كارتون",
            "company_unit_price": 30000,
            "mfec_share_type": "fixed",
            "mfec_share_value": 3000,
            "effective_from": "2026-01-01",
        })
        kilo = await client.post(f"/api/v1/admin/financial/companies/{company_id}/pricing-items", json={
            "name": "كيلو",
            "unit": "كيلو",
            "company_unit_price": 1000,
            "mfec_share_type": "percentage",
            "mfec_share_value": 10,
            "effective_from": "2026-01-01",
        })
        assert carton.status_code == 200, carton.text
        assert kilo.status_code == 200, kilo.text
        carton_id = carton.json()["id"]
        kilo_id = kilo.json()["id"]

        async with session_maker() as fixture_session:
            member = Registrations(
                business_name="متجر أحمد",
                merchant_name="أحمد",
                phone="07801112233",
                governorate="بغداد",
                area="الكرادة",
                business_type="تجارة",
                image_key="test",
                status="approved",
                membership_number="MF-MONTHLY-1",
                membership_status="active",
                user_id="monthly-test",
            )
            fixture_session.add(member)
            await fixture_session.commit()
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
                {
                    "pricing_item_id": kilo_id,
                    "is_active": True,
                    "unit_price_override": 1200,
                    "mfec_share_type_override": "percentage",
                    "mfec_share_value_override": 15,
                },
            ],
        })
        assert account.status_code == 200, account.text

        grid1 = await client.get(
            f"/api/v1/admin/financial/monthly-statements/grid"
            f"?company_id={company_id}&accounting_year={year}&accounting_month={month}"
        )
        assert grid1.status_code == 200, grid1.text
        items = grid1.json()["items"]
        assert grid1.json()["row_count"] == 2
        assert len(items) == 2
        assert {row["pricing_item_name"] for row in items} == {"كارتون", "كيلو"}
        assert all(row["member_name"] == "أحمد" for row in items)
        assert all(row["company_name"] == "شركة إدخال شهري" for row in items)

        by_name = {row["pricing_item_name"]: row for row in items}
        assert by_name["كارتون"]["unit"] == "كارتون"
        assert by_name["كارتون"]["effective_unit_price"] == 30000
        assert by_name["كارتون"]["effective_mfec_share_type"] == "fixed"
        assert by_name["كارتون"]["effective_mfec_share_value"] == 3000
        # Override on kilo link must win over company price/share.
        assert by_name["كيلو"]["effective_unit_price"] == 1200
        assert by_name["كيلو"]["effective_mfec_share_type"] == "percentage"
        assert by_name["كيلو"]["effective_mfec_share_value"] == 15

        qty_carton = 40
        qty_kilo = 350
        expected_carton_gross = qty_carton * 30000
        expected_carton_mfec = qty_carton * 3000
        expected_kilo_gross = qty_kilo * 1200
        expected_kilo_mfec = expected_kilo_gross * Decimal("0.15")

        save1 = await client.put("/api/v1/admin/financial/statements/bulk", json={
            "company_id": company_id,
            "accounting_year": year,
            "accounting_month": month,
            "period_start": f"{year}-{month:02d}-01",
            "period_end": f"{year}-{month:02d}-31",
            "received_at": f"{year}-{month:02d}-05",
            "notes": "كشف أصلي تجريبي",
            "lines": [
                {"account_item_id": by_name["كارتون"]["account_item_id"], "quantity": qty_carton, "excluded": False},
                {"account_item_id": by_name["كيلو"]["account_item_id"], "quantity": qty_kilo, "excluded": False},
            ],
        })
        assert save1.status_code == 200, save1.text
        body = save1.json()
        assert body["saved"] == 2
        assert body.get("failed", 0) == 0
        statement_id = body["statement_id"]
        assert statement_id

        # Refresh / reopen same company+period in a new request (new DB session).
        grid2 = await client.get(
            f"/api/v1/admin/financial/monthly-statements/grid"
            f"?company_id={company_id}&accounting_year={year}&accounting_month={month}"
        )
        assert grid2.status_code == 200, grid2.text
        assert grid2.json()["statement_id"] == statement_id
        assert grid2.json()["notes"] == "كشف أصلي تجريبي"
        assert grid2.json()["received_at"] == f"{year}-{month:02d}-05"
        reopened = {row["pricing_item_name"]: row for row in grid2.json()["items"]}
        assert reopened["كارتون"]["quantity"] == qty_carton
        assert reopened["كارتون"]["gross_business_amount"] == expected_carton_gross
        assert reopened["كارتون"]["mfec_due_amount"] == expected_carton_mfec
        assert reopened["كيلو"]["quantity"] == qty_kilo
        assert reopened["كيلو"]["gross_business_amount"] == float(expected_kilo_gross)
        assert reopened["كيلو"]["mfec_due_amount"] == float(expected_kilo_mfec)

        # Edit quantities and save again — correct rows update.
        save2 = await client.put("/api/v1/admin/financial/statements/bulk", json={
            "company_id": company_id,
            "accounting_year": year,
            "accounting_month": month,
            "received_at": f"{year}-{month:02d}-05",
            "notes": "كشف أصلي تجريبي",
            "lines": [
                {"account_item_id": by_name["كارتون"]["account_item_id"], "quantity": 41, "excluded": False},
                {"account_item_id": by_name["كيلو"]["account_item_id"], "quantity": 360, "excluded": False},
            ],
        })
        assert save2.status_code == 200, save2.text
        assert save2.json()["saved"] == 2
        assert save2.json()["statement_id"] == statement_id

        grid3 = await client.get(
            f"/api/v1/admin/financial/monthly-statements/grid"
            f"?company_id={company_id}&accounting_year={year}&accounting_month={month}"
        )
        assert grid3.status_code == 200, grid3.text
        updated = {row["pricing_item_name"]: row for row in grid3.json()["items"]}
        assert updated["كارتون"]["quantity"] == 41
        assert updated["كارتون"]["gross_business_amount"] == 41 * 30000
        assert updated["كارتون"]["mfec_due_amount"] == 41 * 3000
        assert updated["كيلو"]["quantity"] == 360
        assert updated["كيلو"]["gross_business_amount"] == 360 * 1200
        assert updated["كيلو"]["mfec_due_amount"] == float(Decimal(360 * 1200) * Decimal("0.15"))

        print(
            "MONTHLY_ENTRY_PASS "
            f"rows={len(items)} saved={body['saved']} "
            f"carton_qty={updated['كارتون']['quantity']} kilo_qty={updated['كيلو']['quantity']} "
            f"statement_id={statement_id}"
        )

    await engine.dispose()
