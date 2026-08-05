"""Admin registrations router — permissions enforced on every mutating/export endpoint."""
import io
import logging
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import Integer, case, cast, extract, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import load_only

from core.database import get_db
from dependencies.auth import get_current_user
from dependencies.permissions import load_user_permissions, require_permission
from models.registrations import Registrations
from routers.audit_log import log_action
from schemas.auth import UserResponse
from services.membership_numbers import allocate_membership_number, ensure_membership_counter
from services.panel_auth import ensure_schema

# Columns required by serialize_registration / RegistrationResponse (avoid SELECT *)
_REGISTRATION_LIST_COLUMNS = (
    Registrations.id,
    Registrations.business_name,
    Registrations.merchant_name,
    Registrations.phone,
    Registrations.governorate,
    Registrations.area,
    Registrations.business_type,
    Registrations.image_key,
    Registrations.notes,
    Registrations.extra_fields,
    Registrations.status,
    Registrations.membership_number,
    Registrations.request_number,
    Registrations.membership_status,
    Registrations.approved_at,
    Registrations.whatsapp_registration_sent,
    Registrations.whatsapp_approval_sent,
    Registrations.whatsapp_last_attempt,
    Registrations.whatsapp_status,
    Registrations.user_id,
    Registrations.last_modified_by,
    Registrations.created_at,
    Registrations.updated_at,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/admin/registrations", tags=["admin-registrations"])

SORTABLE_FIELDS = {
    "membership_number",
    "business_name",
    "merchant_name",
    "phone",
    "governorate",
    "status",
    "membership_status",
    "created_at",
    "approved_at",
    "last_modified_by",
    "updated_at",
    "id",
}


def get_actor_name(current_user: UserResponse) -> str:
    """Sync fallback from JWT claims (prefer resolve_actor_name with DB when available)."""
    from services.actor import actor_from_user

    return actor_from_user(current_user)


class StatusUpdateRequest(BaseModel):
    status: str


class MembershipStatusUpdateRequest(BaseModel):
    membership_status: str


class NextMembershipNumberRequest(BaseModel):
    next_number: int


class NextApplicationNumberRequest(BaseModel):
    next_number: int


class ManualMemberRequest(BaseModel):
    business_name: str
    merchant_name: str
    phone: str
    governorate: str
    area: str
    business_type: str
    notes: Optional[str] = ""
    membership_status: Optional[str] = "active"
    image_key: Optional[str] = "manual_entry"


class RegistrationResponse(BaseModel):
    id: int
    business_name: str
    merchant_name: str
    phone: str
    governorate: str
    area: str
    business_type: Optional[str] = None
    image_key: str
    notes: Optional[str] = None
    status: str
    membership_number: Optional[str] = None
    request_number: Optional[str] = None
    membership_status: Optional[str] = None
    approved_at: Optional[str] = None
    whatsapp_registration_sent: Optional[bool] = False
    whatsapp_approval_sent: Optional[bool] = False
    whatsapp_last_attempt: Optional[str] = None
    whatsapp_status: Optional[str] = "none"
    user_id: str
    last_modified_by: Optional[str] = None
    extra_fields: Optional[dict] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    class Config:
        from_attributes = True


class RegistrationListResponse(BaseModel):
    items: List[RegistrationResponse]
    total: int
    skip: int
    limit: int


class StatsResponse(BaseModel):
    total: int
    pending: int
    approved: int
    rejected: int
    active_members: int
    suspended_members: int


def serialize_registration(item, form_settings: Optional[dict] = None) -> RegistrationResponse:
    from services.extra_fields import resolve_member_extra_fields

    mn = getattr(item, "membership_number", None) or None
    if mn == "":
        mn = None
    extras = resolve_member_extra_fields(item, form_settings)
    return RegistrationResponse(
        id=item.id,
        business_name=item.business_name,
        merchant_name=item.merchant_name,
        phone=item.phone,
        governorate=item.governorate,
        area=item.area,
        business_type=getattr(item, "business_type", None),
        image_key=item.image_key,
        notes=item.notes,
        status=item.status,
        membership_number=mn,
        request_number=getattr(item, "request_number", None) or None,
        membership_status=getattr(item, "membership_status", None) or None,
        approved_at=getattr(item, "approved_at", None) or None,
        whatsapp_registration_sent=getattr(item, "whatsapp_registration_sent", False),
        whatsapp_approval_sent=getattr(item, "whatsapp_approval_sent", False),
        whatsapp_last_attempt=getattr(item, "whatsapp_last_attempt", None) or None,
        whatsapp_status=getattr(item, "whatsapp_status", "none") or "none",
        user_id=item.user_id,
        last_modified_by=getattr(item, "last_modified_by", None) or None,
        extra_fields=extras or None,
        created_at=str(item.created_at) if item.created_at else None,
        updated_at=str(item.updated_at) if item.updated_at else None,
    )


def apply_filters(stmt, count_stmt, query, status, membership_status, governorate, year, month, day):
    if status:
        stmt = stmt.where(Registrations.status == status)
        count_stmt = count_stmt.where(Registrations.status == status)
    if membership_status:
        stmt = stmt.where(Registrations.membership_status == membership_status)
        count_stmt = count_stmt.where(Registrations.membership_status == membership_status)
    if governorate:
        stmt = stmt.where(Registrations.governorate == governorate)
        count_stmt = count_stmt.where(Registrations.governorate == governorate)
    if year:
        stmt = stmt.where(extract("year", Registrations.created_at) == year)
        count_stmt = count_stmt.where(extract("year", Registrations.created_at) == year)
    if month:
        stmt = stmt.where(extract("month", Registrations.created_at) == month)
        count_stmt = count_stmt.where(extract("month", Registrations.created_at) == month)
    if day:
        stmt = stmt.where(extract("day", Registrations.created_at) == day)
        count_stmt = count_stmt.where(extract("day", Registrations.created_at) == day)
    if query:
        search_term = f"%{query}%"
        search_filter = (
            Registrations.business_name.ilike(search_term)
            | Registrations.merchant_name.ilike(search_term)
            | Registrations.phone.ilike(search_term)
            | Registrations.area.ilike(search_term)
            | Registrations.membership_number.ilike(search_term)
        )
        stmt = stmt.where(search_filter)
        count_stmt = count_stmt.where(search_filter)
    return stmt, count_stmt


def parse_id_list(ids: Optional[str]):
    """Optional comma-separated registration IDs for export/print subsets."""
    if not ids:
        return None
    out = []
    for part in str(ids).split(","):
        part = part.strip()
        if part.isdigit():
            out.append(int(part))
    return out or None


def apply_sort(stmt, sort: Optional[str]):
    if not sort:
        return stmt.order_by(Registrations.created_at.desc())

    descending = sort.startswith("-")
    field = sort[1:] if descending else sort
    if field not in SORTABLE_FIELDS:
        return stmt.order_by(Registrations.created_at.desc())

    if field == "membership_number":
        num_expr = cast(func.substr(Registrations.membership_number, 4), Integer)
        order_expr = case(
            (
                (Registrations.membership_number.is_(None))
                | (Registrations.membership_number == ""),
                0 if descending else 999999999,
            ),
            else_=num_expr,
        )
        return stmt.order_by(order_expr.desc() if descending else order_expr.asc())

    col = getattr(Registrations, field)
    return stmt.order_by(col.desc() if descending else col.asc())


@router.get("/check-admin")
async def check_admin_access(
    current_user: UserResponse = Depends(require_permission("view")),
    db: AsyncSession = Depends(get_db),
):
    await ensure_schema()
    await ensure_membership_counter(db)
    perms = await load_user_permissions(db, current_user)
    return {
        "authorized": True,
        "email": current_user.email,
        "name": current_user.name,
        "permissions": perms,
        "is_super_admin": bool(getattr(current_user, "is_super_admin", False)),
    }


@router.get("/stats", response_model=StatsResponse)
async def get_stats(
    current_user: UserResponse = Depends(require_permission("view")),
    db: AsyncSession = Depends(get_db),
):
    try:
        # Single-pass conditional aggregates (one table scan / index use) instead of 6 COUNTs
        row = (
            await db.execute(
                select(
                    func.count(Registrations.id),
                    func.coalesce(
                        func.sum(case((Registrations.status == "pending", 1), else_=0)), 0
                    ),
                    func.coalesce(
                        func.sum(case((Registrations.status == "approved", 1), else_=0)), 0
                    ),
                    func.coalesce(
                        func.sum(case((Registrations.status == "rejected", 1), else_=0)), 0
                    ),
                    func.coalesce(
                        func.sum(case((Registrations.membership_status == "active", 1), else_=0)), 0
                    ),
                    func.coalesce(
                        func.sum(case((Registrations.membership_status == "suspended", 1), else_=0)),
                        0,
                    ),
                )
            )
        ).one()
        return StatsResponse(
            total=int(row[0] or 0),
            pending=int(row[1] or 0),
            approved=int(row[2] or 0),
            rejected=int(row[3] or 0),
            active_members=int(row[4] or 0),
            suspended_members=int(row[5] or 0),
        )
    except Exception as e:
        logger.error(f"Error fetching stats: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="خطأ في جلب الإحصائيات")


@router.get("", response_model=RegistrationListResponse)
async def get_all_registrations(
    query: str = Query(None),
    status: str = Query(None),
    membership_status: str = Query(None),
    governorate: str = Query(None),
    year: int = Query(None),
    month: int = Query(None),
    day: int = Query(None),
    sort: str = Query(None),
    sort_by: str = Query(None),
    sort_order: str = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    current_user: UserResponse = Depends(require_permission("view")),
    db: AsyncSession = Depends(get_db),
):
    try:
        # Prefer explicit sort_by/sort_order when provided
        effective_sort = sort
        if sort_by:
            field = sort_by.strip()
            order = (sort_order or "asc").strip().lower()
            effective_sort = f"-{field}" if order == "desc" else field
        if not effective_sort:
            effective_sort = "-created_at"

        stmt = select(Registrations).options(load_only(*_REGISTRATION_LIST_COLUMNS))
        count_stmt = select(func.count(Registrations.id))
        stmt, count_stmt = apply_filters(
            stmt, count_stmt, query, status, membership_status, governorate, year, month, day
        )
        stmt = apply_sort(stmt, effective_sort)
        total = (await db.execute(count_stmt)).scalar() or 0
        result = await db.execute(stmt.offset(skip).limit(limit))
        items = result.scalars().all()
        from services.app_settings_service import get_registration_form_settings

        form_settings = await get_registration_form_settings(db)

        return RegistrationListResponse(
            items=[serialize_registration(item, form_settings) for item in items],
            total=total,
            skip=skip,
            limit=limit,
        )
    except Exception as e:
        logger.error(f"Error fetching registrations: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="خطأ في جلب البيانات")


@router.get("/export-all")
async def export_all_registrations(
    query: str = Query(None),
    status: str = Query(None),
    membership_status: str = Query(None),
    governorate: str = Query(None),
    year: int = Query(None),
    month: int = Query(None),
    day: int = Query(None),
    sort: str = Query("-created_at"),
    current_user: UserResponse = Depends(require_permission("export")),
    db: AsyncSession = Depends(get_db),
):
    try:
        stmt = select(Registrations)
        count_stmt = select(func.count(Registrations.id))
        stmt, _ = apply_filters(
            stmt, count_stmt, query, status, membership_status, governorate, year, month, day
        )
        stmt = apply_sort(stmt, sort)
        result = await db.execute(stmt)
        items = result.scalars().all()
        from services.app_settings_service import get_registration_form_settings
        from services.extra_fields import resolve_member_extra_fields, dynamic_field_defs

        form_settings = await get_registration_form_settings(db)
        data = []
        for item in items:
            extras = resolve_member_extra_fields(item, form_settings)
            data.append(
                {
                    "id": item.id,
                    "business_name": item.business_name,
                    "merchant_name": item.merchant_name,
                    "phone": item.phone,
                    "governorate": item.governorate,
                    "area": item.area,
                    "business_type": getattr(item, "business_type", "") or "",
                    "image_key": item.image_key,
                    "notes": item.notes or "",
                    "status": item.status,
                    "membership_number": getattr(item, "membership_number", "") or "",
                    "membership_status": getattr(item, "membership_status", "") or "",
                    "approved_at": getattr(item, "approved_at", "") or "",
                    "last_modified_by": getattr(item, "last_modified_by", "") or "",
                    "extra_fields": extras,
                    "created_at": str(item.created_at) if item.created_at else "",
                    "updated_at": str(item.updated_at) if item.updated_at else "",
                }
            )
        await log_action(db, "export", current_user.email, details=f"Exported {len(data)} records as JSON")
        return {
            "items": data,
            "total": len(data),
            "exported_at": datetime.utcnow().isoformat(),
            "dynamic_fields": [
                {"id": f.get("id"), "label": f.get("label")} for f in dynamic_field_defs(form_settings)
            ],
        }
    except Exception as e:
        logger.error(f"Error exporting: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="خطأ في التصدير")


@router.get("/export-xlsx")
async def export_xlsx(
    query: str = Query(None),
    status: str = Query(None),
    membership_status: str = Query(None),
    governorate: str = Query(None),
    year: int = Query(None),
    month: int = Query(None),
    day: int = Query(None),
    sort: str = Query("-created_at"),
    max_records: int = Query(0, ge=0, le=5000),
    ids: str = Query(None),
    current_user: UserResponse = Depends(require_permission("export")),
    db: AsyncSession = Depends(get_db),
):
    """Generate a branded professional .xlsx workbook (openpyxl)."""
    try:
        from services.excel_report import build_members_xlsx
        from services.app_settings_service import get_brand_settings, get_registration_form_settings
    except ImportError as e:
        logger.error("excel_report import failed: %s", e)
        raise HTTPException(status_code=500, detail="مكتبة Excel غير مثبتة على الخادم")

    try:
        await ensure_schema()
        stmt = select(Registrations)
        count_stmt = select(func.count(Registrations.id))
        id_list = parse_id_list(ids)
        if id_list:
            stmt = stmt.where(Registrations.id.in_(id_list))
        else:
            stmt, _ = apply_filters(
                stmt, count_stmt, query, status, membership_status, governorate, year, month, day
            )
        stmt = apply_sort(stmt, sort)
        if max_records and max_records > 0:
            stmt = stmt.limit(max_records)
        result = await db.execute(stmt)
        items = result.scalars().all()
        form_settings = await get_registration_form_settings(db)
        brand = await get_brand_settings(db)

        # Persist notes→extra_fields once so DB and future reports stay in sync
        from services.extra_fields import backfill_extra_fields_from_notes

        try:
            await backfill_extra_fields_from_notes(db, form_settings)
        except Exception as bf_err:
            logger.warning("extra_fields backfill skipped: %s", bf_err)

        content = build_members_xlsx(
            items,
            exported_by=get_actor_name(current_user),
            exported_at=datetime.now(),
            brand=brand,
            form_settings=form_settings,
        )

        await log_action(
            db, "export_xlsx", current_user.email, details=f"Exported {len(items)} records as XLSX"
        )

        filename = f"members_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.xlsx"
        headers = {
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "Cache-Control": "no-store",
        }
        return StreamingResponse(
            io.BytesIO(content),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers=headers,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error exporting xlsx: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="خطأ في تصدير Excel")


@router.get("/print-data")
async def print_data(
    query: str = Query(None),
    status: str = Query(None),
    membership_status: str = Query(None),
    governorate: str = Query(None),
    year: int = Query(None),
    month: int = Query(None),
    day: int = Query(None),
    sort: str = Query("-created_at"),
    scope: str = Query("filtered"),
    skip: int = Query(0, ge=0),
    limit: int = Query(500, ge=1, le=5000),
    max_records: int = Query(0, ge=0, le=5000),
    ids: str = Query(None),
    current_user: UserResponse = Depends(require_permission("export")),
    db: AsyncSession = Depends(get_db),
):
    """Return rows for browser print view (requires export permission)."""
    try:
        from services.app_settings_service import get_brand_settings

        await ensure_schema()
        stmt = select(Registrations)
        count_stmt = select(func.count(Registrations.id))
        id_list = parse_id_list(ids)
        if id_list:
            stmt = stmt.where(Registrations.id.in_(id_list))
            count_stmt = count_stmt.where(Registrations.id.in_(id_list))
        elif scope != "all":
            stmt, count_stmt = apply_filters(
                stmt, count_stmt, query, status, membership_status, governorate, year, month, day
            )
        stmt = apply_sort(stmt, sort)
        total = (await db.execute(count_stmt)).scalar() or 0
        if id_list:
            pass
        elif scope == "current":
            stmt = stmt.offset(skip).limit(limit)
        elif max_records and max_records > 0:
            stmt = stmt.limit(max_records)
        result = await db.execute(stmt)
        items = result.scalars().all()
        brand = await get_brand_settings(db)
        from services.app_settings_service import get_registration_form_settings
        from services.extra_fields import dynamic_field_defs, backfill_extra_fields_from_notes

        form_settings = await get_registration_form_settings(db)
        try:
            await backfill_extra_fields_from_notes(db, form_settings)
        except Exception as bf_err:
            logger.warning("extra_fields backfill skipped: %s", bf_err)

        dyn = [{"id": f.get("id"), "label": f.get("label")} for f in dynamic_field_defs(form_settings)]
        await log_action(
            db,
            "print",
            current_user.email,
            details=f"Print scope={scope} rows={len(items)}",
        )
        return {
            "items": [serialize_registration(item, form_settings) for item in items],
            "total": len(items),
            "filtered_total": total,
            "scope": scope,
            "printed_by": get_actor_name(current_user),
            "printed_at": datetime.now().isoformat(timespec="seconds"),
            "brand": brand,
            "dynamic_fields": dyn,
            "org_name": brand.get("system_name"),
            "org_abbr": brand.get("org_abbr"),
            "report_title": brand.get("report_title"),
            "sponsor": brand.get("footer_text"),
            "website": brand.get("website"),
            "email": brand.get("email"),
            "phone": brand.get("phone"),
            "logo": brand.get("report_logo") or brand.get("system_logo"),
            "primary_color": brand.get("primary_color"),
            "secondary_color": brand.get("secondary_color"),
        }
    except Exception as e:
        logger.error(f"Error preparing print data: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="خطأ في تجهيز بيانات الطباعة")


@router.get("/next-membership-number")
async def get_next_membership_number_api(
    current_user: UserResponse = Depends(require_permission("edit")),
    db: AsyncSession = Depends(get_db),
):
    from services.membership_numbers import get_next_membership_number, format_membership

    await ensure_schema()
    # get_next_membership_number → ensure_membership_counter (cheap when counter exists)
    n = await get_next_membership_number(db)
    return {
        "next_number": n,
        "preview": format_membership(n),
        "requested_by": get_actor_name(current_user),
    }


async def _save_next_membership_number(
    data: NextMembershipNumberRequest,
    request: Request,
    current_user: UserResponse,
    db: AsyncSession,
):
    from services.actor import resolve_actor_name
    from services.membership_numbers import set_next_membership_number, format_membership

    await ensure_schema()
    try:
        n = await set_next_membership_number(db, int(data.next_number))
        await db.commit()
    except ValueError as e:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        await db.rollback()
        raise

    actor = await resolve_actor_name(db, current_user)
    await log_action(
        db,
        "set_next_membership_number",
        current_user.email,
        details=f"Next membership set to {format_membership(n)} by {actor}",
        ip_address=request.client.host if request.client else None,
    )
    return {
        "success": True,
        "next_number": n,
        "preview": format_membership(n),
        "message": f"سيحصل العضو الجديد التالي على {format_membership(n)}",
    }


@router.api_route("/next-membership-number", methods=["POST", "PUT", "PATCH"])
async def save_next_membership_number_api(
    data: NextMembershipNumberRequest,
    request: Request,
    current_user: UserResponse = Depends(require_permission("edit")),
    db: AsyncSession = Depends(get_db),
):
    """Save next membership number (POST/PUT/PATCH — same handler)."""
    return await _save_next_membership_number(data, request, current_user, db)


@router.get("/next-application-number")
async def get_next_application_number_api(
    current_user: UserResponse = Depends(require_permission("edit")),
    db: AsyncSession = Depends(get_db),
):
    from services.membership_numbers import (
        get_next_application_number,
        format_application,
    )

    await ensure_schema()
    # get_next_application_number → ensure_application_counter (cheap when counter exists)
    n = await get_next_application_number(db)
    return {
        "next_number": n,
        "preview": format_application(n),
        "requested_by": get_actor_name(current_user),
    }


async def _save_next_application_number(
    data: NextApplicationNumberRequest,
    request: Request,
    current_user: UserResponse,
    db: AsyncSession,
):
    from services.actor import resolve_actor_name
    from services.membership_numbers import set_next_application_number, format_application

    await ensure_schema()
    try:
        n = await set_next_application_number(db, int(data.next_number))
        await db.commit()
    except ValueError as e:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        await db.rollback()
        raise

    actor = await resolve_actor_name(db, current_user)
    await log_action(
        db,
        "set_next_application_number",
        current_user.email,
        details=f"Next application set to {format_application(n)} by {actor}",
        ip_address=request.client.host if request.client else None,
    )
    return {
        "success": True,
        "next_number": n,
        "preview": format_application(n),
        "message": f"سيحصل الطلب الجديد التالي على {format_application(n)}",
    }


@router.api_route("/next-application-number", methods=["POST", "PUT", "PATCH"])
async def save_next_application_number_api(
    data: NextApplicationNumberRequest,
    request: Request,
    current_user: UserResponse = Depends(require_permission("edit")),
    db: AsyncSession = Depends(get_db),
):
    return await _save_next_application_number(data, request, current_user, db)


@router.put("/{registration_id}/status")
async def update_registration_status(
    registration_id: int,
    data: StatusUpdateRequest,
    request: Request,
    current_user: UserResponse = Depends(require_permission("edit")),
    db: AsyncSession = Depends(get_db),
):
    if data.status not in ["approved", "rejected", "pending"]:
        raise HTTPException(status_code=400, detail="حالة غير صالحة")

    try:
        result = await db.execute(select(Registrations).where(Registrations.id == registration_id))
        registration = result.scalar_one_or_none()
        if not registration:
            raise HTTPException(status_code=404, detail="الطلب غير موجود")

        old_status = registration.status
        registration.status = data.status
        from services.actor import resolve_actor_name

        registration.last_modified_by = await resolve_actor_name(db, current_user)

        if data.status == "approved" and not registration.membership_number:
            registration.membership_number = await allocate_membership_number(db)
            registration.membership_status = "active"
            registration.approved_at = datetime.utcnow().isoformat()

        await db.commit()
        await db.refresh(registration)

        await log_action(
            db,
            f"status_{data.status}",
            current_user.email,
            target_id=registration_id,
            details=f"Changed from {old_status} to {data.status}. MN: {registration.membership_number or 'N/A'}",
            ip_address=request.client.host if request.client else None,
        )

        return {
            "message": "تم تحديث الحالة بنجاح",
            "id": registration.id,
            "status": registration.status,
            "membership_number": registration.membership_number,
        }
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error updating status: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="خطأ في تحديث الحالة")


@router.put("/{registration_id}/membership-status")
async def update_membership_status(
    registration_id: int,
    data: MembershipStatusUpdateRequest,
    request: Request,
    current_user: UserResponse = Depends(require_permission("edit")),
    db: AsyncSession = Depends(get_db),
):
    if data.membership_status not in ["active", "suspended", "expired"]:
        raise HTTPException(status_code=400, detail="حالة عضوية غير صالحة")

    try:
        result = await db.execute(select(Registrations).where(Registrations.id == registration_id))
        registration = result.scalar_one_or_none()
        if not registration:
            raise HTTPException(status_code=404, detail="الطلب غير موجود")

        old_ms = registration.membership_status
        registration.membership_status = data.membership_status
        from services.actor import resolve_actor_name

        registration.last_modified_by = await resolve_actor_name(db, current_user)
        await db.commit()

        await log_action(
            db,
            "update_membership",
            current_user.email,
            target_id=registration_id,
            details=f"Membership status: {old_ms} -> {data.membership_status}",
            ip_address=request.client.host if request.client else None,
        )

        return {
            "message": "تم تحديث حالة العضوية",
            "id": registration.id,
            "membership_status": registration.membership_status,
        }
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error updating membership: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="خطأ في تحديث حالة العضوية")


@router.post("/add-member")
async def add_member_manually(
    data: ManualMemberRequest,
    request: Request,
    current_user: UserResponse = Depends(require_permission("add")),
    db: AsyncSession = Depends(get_db),
):
    try:
        from services.actor import resolve_actor_name

        membership_number = await allocate_membership_number(db)
        actor = await resolve_actor_name(db, current_user)

        new_member = Registrations(
            business_name=data.business_name,
            merchant_name=data.merchant_name,
            phone=data.phone,
            governorate=data.governorate,
            area=data.area,
            business_type=data.business_type,
            image_key=data.image_key or "manual_entry",
            notes=data.notes or "",
            status="approved",
            membership_number=membership_number,
            request_number=None,
            membership_status=data.membership_status or "active",
            approved_at=datetime.utcnow().isoformat(),
            whatsapp_registration_sent=False,
            whatsapp_approval_sent=False,
            whatsapp_last_attempt="",
            whatsapp_status="none",
            user_id=current_user.id,
            last_modified_by=actor,
        )

        db.add(new_member)
        await db.commit()
        await db.refresh(new_member)

        await log_action(
            db,
            "add_member",
            current_user.email,
            target_id=new_member.id,
            details=f"Manual member: {data.business_name} - {data.merchant_name} - {membership_number}",
            ip_address=request.client.host if request.client else None,
        )

        return {
            "message": "تم إضافة العضو بنجاح",
            "id": new_member.id,
            "membership_number": new_member.membership_number,
        }
    except Exception as e:
        await db.rollback()
        logger.error(f"Error adding member: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="خطأ في إضافة العضو")


@router.delete("/{registration_id}")
async def delete_registration(
    registration_id: int,
    request: Request,
    current_user: UserResponse = Depends(require_permission("delete")),
    db: AsyncSession = Depends(get_db),
):
    try:
        result = await db.execute(select(Registrations).where(Registrations.id == registration_id))
        registration = result.scalar_one_or_none()
        if not registration:
            raise HTTPException(status_code=404, detail="الطلب غير موجود")

        reg_info = f"{registration.business_name} - {registration.merchant_name}"
        await db.delete(registration)
        await db.commit()

        await log_action(
            db,
            "delete",
            current_user.email,
            target_id=registration_id,
            details=f"Deleted: {reg_info}",
            ip_address=request.client.host if request.client else None,
        )

        return {"message": "تم حذف الطلب بنجاح", "id": registration_id}
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error deleting: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="خطأ في حذف الطلب")
