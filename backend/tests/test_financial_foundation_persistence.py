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
async def test_company_and_member_pricing_persist_across_api_sessions(tmp_path: Path):
    """Exercise the production routes against a committed, reopened SQLite database."""
    database_path = tmp_path / "financial-foundation.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path}")
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async def isolated_db_session():
        async with session_maker() as session:
            yield session

    async def admin_user():
        return UserResponse(
            id="test-admin",
            email="test@example.com",
            name="مختبر",
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
        service_response = await client.post(
            "/api/v1/admin/financial/service-types",
            json={"name": "شركة شحن", "code": "shipping_company"},
        )
        assert service_response.status_code == 200
        service_id = service_response.json()["id"]

        company_response = await client.post(
            "/api/v1/admin/financial/companies",
            json={
                "name": "شركة اختبار الحفظ",
                "service_type_id": service_id,
                "owner_name": "مالك الاختبار",
                "address": "بغداد",
                "mobile": "07700000000",
                "cooperation_started_at": "2026-08-01",
                "cooperation_status": "active",
                "status": "active",
                "notes": "اختبار حفظ معزول",
            },
        )
        assert company_response.status_code == 200
        company_id = company_response.json()["id"]
        assert company_id

        # This request receives a fresh SQLAlchemy session from the dependency.
        companies_response = await client.get("/api/v1/admin/financial/companies")
        assert companies_response.status_code == 200
        persisted_company = next(
            company for company in companies_response.json()["items"]
            if company["id"] == company_id
        )
        assert persisted_company["service_type_name"] == "شركة شحن"

        pricing_response = await client.post(
            f"/api/v1/admin/financial/companies/{company_id}/pricing-items",
            json={
                "name": "كارتون",
                "unit": "كارتون",
                "company_unit_price": 30000,
                "mfec_share_type": "fixed",
                "mfec_share_value": 3000,
                "effective_from": "2026-01-01",
            },
        )
        assert pricing_response.status_code == 200
        pricing_item_id = pricing_response.json()["id"]

        async with session_maker() as fixture_session:
            member = Registrations(
                business_name="متجر الاختبار",
                merchant_name="عضو الاختبار",
                phone="07800000000",
                governorate="بغداد",
                area="الكرادة",
                business_type="تجارة",
                image_key="test",
                status="approved",
                membership_number="MF-FOUNDATION-1",
                membership_status="active",
                user_id="foundation-test",
            )
            fixture_session.add(member)
            await fixture_session.commit()
            member_id = member.id

        account_response = await client.post(
            "/api/v1/admin/financial/member-accounts",
            json={
                "member_id": member_id,
                "company_id": company_id,
                "registered_name": "عضو الاختبار",
                "customer_portal_url": None,
                "started_at": "2026-08-01",
                "status": "active",
                "is_active": True,
                "items": [{"pricing_item_id": pricing_item_id, "is_active": True}],
            },
        )
        assert account_response.status_code == 200
        account_id = account_response.json()["id"]
        assert account_response.json()["saved_items"] == 1

        # Both reloads use new sessions and therefore prove committed persistence.
        accounts_response = await client.get(
            f"/api/v1/admin/financial/member-accounts?member_id={member_id}&company_id={company_id}"
        )
        items_response = await client.get(
            f"/api/v1/admin/financial/member-accounts/{account_id}/items"
        )
        assert accounts_response.status_code == 200
        assert items_response.status_code == 200
        assert accounts_response.json()["items"][0]["id"] == account_id
        assigned_item = items_response.json()["items"][0]
        assert assigned_item["pricing_item_id"] == pricing_item_id
        assert assigned_item["unit_price_override"] is None
        assert assigned_item["mfec_share_type_override"] is None
        assert assigned_item["mfec_share_value_override"] is None
        assert assigned_item["effective_unit_price"] == 30000
        assert assigned_item["effective_mfec_share_type"] == "fixed"
        assert assigned_item["effective_mfec_share_value"] == 3000
        print(
            "PERSISTENCE_EVIDENCE "
            f"backend=sqlite-file company_status={company_response.status_code} "
            f"company_id={company_id} account_status={account_response.status_code} "
            f"account_id={account_id} reopened_items={len(items_response.json()['items'])} "
            "effective_price=30000 effective_share=fixed:3000"
        )

    await engine.dispose()
