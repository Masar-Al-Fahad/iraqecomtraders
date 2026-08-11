"""End-to-end persistence for the companies/contracts page only."""
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


@pytest.mark.asyncio
async def test_companies_page_shipping_contract_pricing_persist(tmp_path: Path):
    database_path = tmp_path / "companies-page.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path}")
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async def isolated_db_session():
        async with session_maker() as session:
            yield session

    async def admin_user():
        return UserResponse(
            id="companies-admin",
            email="companies@example.com",
            name="مختبر الشركات",
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
        # 1) Ensure canonical service types and create shipping company
        services = await client.get("/api/v1/admin/financial/service-types?ensure_canonical=true")
        assert services.status_code == 200
        shipping = next(item for item in services.json()["items"] if item["code"] == "shipping")
        assert shipping["name"] == "شحن"

        company_name = "شركة شحن اختبار الصفحة"
        create = await client.post("/api/v1/admin/financial/companies", json={
            "name": company_name,
            "service_type_id": shipping["id"],
            "owner_name": "مالك الشحن",
            "address": "بغداد",
            "mobile": "07701112233",
            "cooperation_started_at": "2026-08-01",
            "cooperation_status": "active",
            "status": "active",
            "notes": "اختبار صفحة الشركات",
            "contact_info": "whatsapp",
        })
        assert create.status_code == 200, create.text
        company_id = create.json()["id"]

        # refresh / new session list
        listed = await client.get("/api/v1/admin/financial/companies")
        assert listed.status_code == 200
        persisted = next(c for c in listed.json()["items"] if c["id"] == company_id)
        assert persisted["name"] == company_name
        assert persisted["service_type_name"] == "شحن"

        # 2) Primary contract metadata
        contract = await client.put(f"/api/v1/admin/financial/companies/{company_id}/primary-contract", json={
            "contract_number": "CTR-2026-001",
            "signed_at": "2026-08-02",
            "effective_from": "2026-08-01",
            "effective_to": None,
            "notes": "عقد أساسي مع مسار الفهد",
        })
        assert contract.status_code == 200, contract.text

        # 3) Two attachments (PDF + Excel metadata only; no real storage bytes needed)
        pdf = await client.post(f"/api/v1/admin/financial/companies/{company_id}/attachments", json={
            "object_key": "financial/contracts/2026/08/test-contract.pdf",
            "original_filename": "contract.pdf",
            "mime_type": "application/pdf",
            "size_bytes": 1234,
            "document_type": "contract",
        })
        assert pdf.status_code == 200, pdf.text
        xlsx = await client.post(f"/api/v1/admin/financial/companies/{company_id}/attachments", json={
            "object_key": "financial/contracts/2026/08/test-prices.xlsx",
            "original_filename": "prices.xlsx",
            "mime_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "size_bytes": 2345,
            "document_type": "price_list",
        })
        assert xlsx.status_code == 200, xlsx.text
        attachments = await client.get(f"/api/v1/admin/financial/companies/{company_id}/attachments")
        assert attachments.status_code == 200
        assert len(attachments.json()["items"]) == 2

        # 4) Pricing items: carton + kilo
        carton = await client.post(f"/api/v1/admin/financial/companies/{company_id}/pricing-items", json={
            "name": "كارتون",
            "unit": "كارتون",
            "company_unit_price": "30000",
            "mfec_share_type": "fixed",
            "mfec_share_value": "3000",
            "effective_from": "2026-08-01",
            "notes": None,
        })
        assert carton.status_code == 200, carton.text
        kilo = await client.post(f"/api/v1/admin/financial/companies/{company_id}/pricing-items", json={
            "name": "كيلو",
            "unit": "كغم",
            "company_unit_price": "2000",
            "mfec_share_type": "percentage",
            "mfec_share_value": "10",
            "effective_from": "2026-08-01",
            "notes": None,
        })
        assert kilo.status_code == 200, kilo.text

        # 5) refresh pricing + contract
        pricing = await client.get(
            f"/api/v1/admin/financial/pricing-items?company_id={company_id}&for_management=true&include_inactive=true"
        )
        assert pricing.status_code == 200
        items = pricing.json()["items"]
        assert {item["name"] for item in items} == {"كارتون", "كيلو"}
        carton_item = next(item for item in items if item["name"] == "كارتون")
        assert carton_item["current_version"]["company_unit_price"] == 30000.0
        assert carton_item["current_version"]["mfec_share_value"] == 3000.0

        primary = await client.get(f"/api/v1/admin/financial/companies/{company_id}/primary-contract")
        assert primary.status_code == 200
        assert primary.json()["contract_number"] == "CTR-2026-001"
        assert primary.json()["signed_at"] == "2026-08-02"

        # Re-open companies list to simulate browser refresh
        listed_again = await client.get("/api/v1/admin/financial/companies")
        assert any(c["id"] == company_id for c in listed_again.json()["items"])
