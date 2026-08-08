from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from core.database import Base
from models.financial import (
    AccountingPeriod,
    CompanyContract,
    FinancialCompany,
    MemberCompanyAccount,
    MonthlyActivity,
    ServiceType,
)
from models.panel_users import PanelUser  # noqa: F401 - register metadata
from models.registrations import Registrations
from routers.financial import (
    MonthlyBulkIn,
    MonthlyRowIn,
    _report_rows,
    list_companies,
    monthly_sheet,
    save_monthly_bulk,
)
from schemas.auth import UserResponse
from services.financial import build_financial_xlsx, calculate_revenue


def test_commission_calculations():
    assert calculate_revenue("fixed_per_operation", 3000, 12) == Decimal("36000.000")
    assert calculate_revenue("percentage", "2.5", 0, 1_000_000) == Decimal("25000.000")
    assert calculate_revenue("monthly_fixed", 500_000, 999) == Decimal("500000.000")
    assert calculate_revenue("custom", 12345, 10) == Decimal("12345.000")
    with pytest.raises(ValueError):
        calculate_revenue("unknown", 1, 1)


@pytest.mark.asyncio
async def test_bulk_entry_snapshot_locking_report_and_xlsx():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    user = UserResponse(
        id="test-user", email="entry@local", name="موظف الإدخال", role="admin",
        permissions={"monthly_entry": True},
    )
    async with maker() as db:
        member = Registrations(
            business_name="متجر اختبار", merchant_name="عضو اختبار", phone="07000000000",
            governorate="بغداد", area="الكرادة", business_type="تجارة",
            image_key="manual_entry", status="approved", membership_number="MF-T001",
            membership_status="active", user_id="test",
        )
        service = ServiceType(name="شركة شحن", code="shipping")
        db.add_all([member, service])
        await db.flush()
        company = FinancialCompany(name="شركة اختبار", service_type_id=service.id, status="active")
        db.add(company)
        await db.flush()
        db.add_all([
            CompanyContract(
                company_id=company.id, version=1, commission_method="fixed_per_operation",
                commission_value=Decimal("3000"), effective_from=date(2026, 1, 1),
                created_by="admin",
            ),
            MemberCompanyAccount(member_id=member.id, company_id=company.id, is_active=True),
        ])
        await db.commit()

        result = await save_monthly_bulk(
            MonthlyBulkIn(
                company_id=company.id, accounting_year=2026, accounting_month=8,
                rows=[MonthlyRowIn(member_id=member.id, operation_count=10)],
                mark_complete=True,
            ),
            user=user, db=db,
        )
        assert result["saved"] == 1
        activity = (await db.execute(select(MonthlyActivity))).scalar_one()
        assert activity.revenue_amount == Decimal("30000.000")
        assert activity.commission_value_snapshot == Decimal("3000.000")
        input_view = await monthly_sheet(
            company_id=company.id, accounting_year=2026, accounting_month=8,
            user=user, db=db,
        )
        assert "revenue_amount" not in input_view["items"][0]
        assert "commission_value" not in input_view["items"][0]
        company_view = await list_companies(
            service_type_id=None, status=None, user=user, db=db,
        )
        assert company_view["items"][0]["current_contract"] is None

        # Changing the contract never mutates the historical monthly snapshot.
        contract = (await db.execute(select(CompanyContract))).scalar_one()
        contract.commission_value = Decimal("4500")
        await db.commit()
        await db.refresh(activity)
        assert activity.revenue_amount == Decimal("30000.000")
        assert activity.commission_value_snapshot == Decimal("3000.000")

        rows = await _report_rows(
            db, year=2026, month=8, company_id=None, service_type_id=None,
            member_id=None, governorate=None,
        )
        assert rows[0]["shipping_operations"] == 10
        assert rows[0]["total_revenue"] == 30000.0
        payload = build_financial_xlsx(rows, "اختبار", "8/2026")
        assert payload[:2] == b"PK"

        period = (await db.execute(select(AccountingPeriod))).scalar_one()
        period.status = "closed"
        await db.commit()
        with pytest.raises(Exception) as exc:
            await save_monthly_bulk(
                MonthlyBulkIn(
                    company_id=company.id, accounting_year=2026, accounting_month=8,
                    rows=[MonthlyRowIn(member_id=member.id, operation_count=11)],
                ),
                user=user, db=db,
            )
        assert getattr(exc.value, "status_code", None) == 409
    await engine.dispose()
