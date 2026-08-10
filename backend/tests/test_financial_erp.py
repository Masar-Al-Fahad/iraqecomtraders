from datetime import date
from decimal import Decimal

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from core.database import Base
from models.financial import (
    FinancialCompany, MemberAccountItem, MemberCompanyAccount, MonthlyEntryLine,
    MonthlyStatement, PricingItem, PricingItemVersion, ReceiptAllocation,
    RevenueReceipt, ServiceType, SettlementBatch,
)
from models.panel_users import PanelUser  # noqa: F401
from models.registrations import Registrations
from routers.financial_erp import (
    AllocationIn, ReopenIn, SettlementIn, StatementBulkIn, StatementLineIn,
    approve_statement, create_settlement, reopen_statement, save_statement_bulk,
)
from schemas.auth import UserResponse
from services.financial_erp import calculate_line, resolve_account_item_pricing, validate_and_add_allocation
from services.panel_auth import normalize_permissions


def test_legacy_permissions_map_to_granular_rbac():
    perms=normalize_permissions({"monthly_entry":True,"view_financial_reports":True})
    assert perms["financial.monthly.enter"] is True
    assert perms["financial.reports.view"] is True
    assert perms["financial.revenues.view"] is False


@pytest_asyncio.fixture
async def db():
    engine=create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn: await conn.run_sync(Base.metadata.create_all)
    maker=async_sessionmaker(engine,expire_on_commit=False)
    async with maker() as session: yield session
    await engine.dispose()


def user(**perms):
    return UserResponse(id="test",email="erp@test",name="مختبر",role="admin",permissions=perms)


async def seed(db):
    member=Registrations(business_name="متجر",merchant_name="عضو",phone="07000000001",governorate="بغداد",area="أ",business_type="تجارة",image_key="x",status="approved",membership_number="MF-E1",membership_status="active",user_id="x")
    service=ServiceType(name="شحن",code="shipping"); db.add_all([member,service]); await db.flush()
    company=FinancialCompany(name="شركة",service_type_id=service.id,status="active"); db.add(company); await db.flush()
    account=MemberCompanyAccount(member_id=member.id,company_id=company.id,status="active",is_active=True,default_unit_price_override=Decimal("28000"))
    item=PricingItem(company_id=company.id,name="كارتون",unit="كارتون"); db.add_all([account,item]); await db.flush()
    version=PricingItemVersion(pricing_item_id=item.id,version=1,company_unit_price=30000,mfec_share_type="fixed",mfec_share_value=3000,effective_from=date(2026,1,1),created_by="admin")
    link=MemberAccountItem(account_id=account.id,pricing_item_id=item.id,unit_price_override=Decimal("27000"),mfec_share_value_override=Decimal("2500"),mfec_share_type_override="fixed",is_active=True)
    db.add_all([version,link]); await db.commit()
    return member,company,account,item,link


@pytest.mark.asyncio
async def test_override_priority_and_snapshot_approval(db):
    member,company,account,item,link=await seed(db)
    _,version,price,share_type,share=await resolve_account_item_pricing(db,link,account,date(2026,8,1))
    assert price==Decimal("27000.000") and share==Decimal("2500.000")
    assert calculate_line(10,price,share_type,share)==(Decimal("270000.000"),Decimal("25000.000"))
    result=await save_statement_bulk(
        StatementBulkIn(company_id=company.id,accounting_year=2026,accounting_month=8,lines=[StatementLineIn(account_item_id=link.id,quantity=10)]),
        user=user(**{"financial.monthly.enter":True}),db=db,
    )
    await approve_statement(result["statement_id"],user=user(**{"financial.monthly.approve":True}),db=db)
    line=(await db.execute(select(MonthlyEntryLine))).scalar_one()
    assert line.company_unit_price_snapshot==Decimal("27000.000")
    link.unit_price_override=Decimal("99999"); await db.commit()
    assert line.company_unit_price_snapshot==Decimal("27000.000")
    with pytest.raises(HTTPException) as exc:
        await save_statement_bulk(
            StatementBulkIn(company_id=company.id,accounting_year=2026,accounting_month=8,lines=[StatementLineIn(account_item_id=link.id,quantity=11)]),
            user=user(**{"financial.monthly.edit":True}),db=db,
        )
    assert exc.value.status_code==409
    await reopen_statement(result["statement_id"],ReopenIn(reason="تصحيح موثق"),user=user(**{"financial.monthly.reopen":True}),db=db)


@pytest.mark.asyncio
async def test_settlement_and_safe_partial_receipt_allocation(db):
    _member,company,_account,_item,link=await seed(db)
    saved=await save_statement_bulk(
        StatementBulkIn(company_id=company.id,accounting_year=2026,accounting_month=8,lines=[StatementLineIn(account_item_id=link.id,quantity=10)]),
        user=user(**{"financial.monthly.enter":True}),db=db,
    )
    await approve_statement(saved["statement_id"],user=user(**{"financial.monthly.approve":True}),db=db)
    line=(await db.execute(select(MonthlyEntryLine))).scalar_one()
    batch=await create_settlement(
        SettlementIn(company_id=company.id,entry_line_ids=[line.id],settled_at=date(2026,9,1)),
        user=user(**{"financial.settlements.create":True}),db=db,
    )
    receipt=RevenueReceipt(receipt_number="R-1",company_id=company.id,received_at=date(2026,9,2),amount=20000,receipt_method="تحويل",description="قبض جزئي",created_by="a",updated_by="a")
    db.add(receipt);await db.commit()
    await validate_and_add_allocation(db,receipt_id=receipt.id,statement_id=None,settlement_batch_id=batch["id"],amount=15000,actor="a")
    await db.commit()
    with pytest.raises(HTTPException) as exc:
        await validate_and_add_allocation(db,receipt_id=receipt.id,statement_id=saved["statement_id"],settlement_batch_id=None,amount=6000,actor="a")
    assert exc.value.status_code==409
    assert (await db.execute(select(ReceiptAllocation))).scalars().all()[0].allocated_amount==Decimal("15000.000")


@pytest.mark.asyncio
async def test_receipt_cannot_cross_companies(db):
    _member,company,_account,_item,_link=await seed(db)
    other=FinancialCompany(name="أخرى",service_type_id=1,status="active");db.add(other);await db.flush()
    statement=MonthlyStatement(company_id=other.id,accounting_year=2026,accounting_month=8,period_start=date(2026,8,1),period_end=date(2026,8,31),entered_by="a")
    receipt=RevenueReceipt(receipt_number="R-2",company_id=company.id,received_at=date(2026,9,2),amount=100,receipt_method="نقدي",description="x",created_by="a",updated_by="a")
    db.add_all([statement,receipt]);await db.commit()
    with pytest.raises(HTTPException) as exc:
        await validate_and_add_allocation(db,receipt_id=receipt.id,statement_id=statement.id,settlement_batch_id=None,amount=50,actor="a")
    assert exc.value.status_code==409
