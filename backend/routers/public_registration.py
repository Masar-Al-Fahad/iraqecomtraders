"""Public registration + Supabase Storage uploads — no authentication required."""
import logging
import re
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.database import get_db
from models.registrations import Registrations
from services import supabase_storage as s3store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/public", tags=["public-registration"])

SAFE_KEY = re.compile(r"^registrations/[A-Za-z0-9._\-]+$")


def _safe_registration_key(object_key: str) -> str:
    key = s3store.normalize_business_key(object_key)
    if not SAFE_KEY.match(key):
        raise HTTPException(status_code=400, detail="مسار الملف غير صالح")
    return key


class UploadUrlRequest(BaseModel):
    bucket_name: str
    object_key: str


class UploadUrlResponse(BaseModel):
    upload_url: str
    object_key: str = ""
    expires_at: str = ""


@router.post("/upload-url", response_model=UploadUrlResponse)
async def get_public_upload_url(data: UploadUrlRequest, request: Request):
    """Return backend upload URL (stores file in Supabase Storage bucket `uploads`)."""
    if data.bucket_name != "business-images":
        raise HTTPException(status_code=403, detail="غير مسموح برفع الملفات إلى هذا المخزن")
    if not data.object_key.startswith("registrations/"):
        raise HTTPException(status_code=403, detail="مسار الملف غير مسموح")

    filename = Path(data.object_key).name
    safe_name = re.sub(r"[^A-Za-z0-9._\-]", "_", filename)
    safe_key = f"registrations/{safe_name}"

    base = str(settings.backend_url).rstrip("/")
    host = request.headers.get("host")
    if host and ("127.0.0.1" in host or "localhost" in host):
        scheme = request.headers.get("x-forwarded-proto", "http")
        base = f"{scheme}://{host}"

    return UploadUrlResponse(
        upload_url=f"{base}/api/v1/public/upload-file?object_key={safe_key}",
        object_key=safe_key,
        expires_at="",
    )


@router.put("/upload-file")
async def upload_file_local(
    request: Request,
    object_key: str = Query(...),
):
    """Accept raw file bytes (PUT) → Supabase Storage uploads/registrations/."""
    safe_key = _safe_registration_key(object_key)
    try:
        content = await request.body()
        if not content:
            raise HTTPException(status_code=400, detail="الملف فارغ")
        if len(content) > 5 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="الحد الأقصى 5MB")
        await s3store.upload_bytes(safe_key, content, upsert=True)
        return {"success": True, "object_key": safe_key, "size": len(content)}
    except HTTPException:
        raise
    except s3store.SupabaseStorageError as e:
        logger.error("Supabase upload failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error(f"Upload failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="فشل في رفع الملف")


@router.post("/upload-file")
async def upload_file_multipart(
    object_key: str = Query(...),
    file: UploadFile = File(...),
):
    """Accept multipart upload → Supabase Storage uploads/registrations/."""
    safe_key = _safe_registration_key(object_key)
    try:
        content = await file.read()
        if not content:
            raise HTTPException(status_code=400, detail="الملف فارغ")
        if len(content) > 5 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="الحد الأقصى 5MB")
        await s3store.upload_bytes(
            safe_key,
            content,
            content_type=file.content_type,
            upsert=True,
        )
        return {"success": True, "object_key": safe_key, "size": len(content)}
    except HTTPException:
        raise
    except s3store.SupabaseStorageError as e:
        logger.error("Supabase multipart upload failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error(f"Multipart upload failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="فشل في رفع الملف")


@router.get("/files/{object_key:path}")
async def get_local_file(object_key: str):
    """Serve registration images from Supabase Storage (redirect to public URL)."""
    safe_key = _safe_registration_key(object_key)
    try:
        return RedirectResponse(url=s3store.public_object_url(safe_key), status_code=302)
    except s3store.SupabaseStorageError as e:
        raise HTTPException(status_code=500, detail=str(e))


class PublicRegistrationRequest(BaseModel):
    business_name: str
    merchant_name: str
    phone: str
    governorate: str
    area: str
    business_type: str
    image_key: str
    notes: Optional[str] = ""
    extra_fields: Optional[dict] = None

    @validator("business_name", "merchant_name", "phone", "governorate", "area", "business_type")
    def not_empty(cls, v):
        if not v or not v.strip():
            raise ValueError("هذا الحقل مطلوب")
        return v.strip()

    @validator("phone")
    def valid_phone(cls, v):
        cleaned = v.strip().replace(" ", "").replace("-", "")
        if len(cleaned) < 10 or len(cleaned) > 15:
            raise ValueError("رقم الهاتف غير صحيح")
        return cleaned


class PublicRegistrationResponse(BaseModel):
    success: bool
    message: str
    request_number: Optional[str] = None


@router.post("/register", response_model=PublicRegistrationResponse)
async def public_register(
    data: PublicRegistrationRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Public registration — no login required."""
    try:
        from services.extra_fields import dumps_extra_fields
        from services.panel_auth import ensure_schema

        await ensure_schema()

        existing = await db.execute(
            select(Registrations).where(
                Registrations.phone == data.phone,
                Registrations.status != "rejected",
            )
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=409,
                detail="يوجد طلب مسجل مسبقاً بهذا الرقم. يرجى الانتظار حتى تتم مراجعة طلبك.",
            )

        image_key = data.image_key or "manual_entry"
        from services.membership_numbers import allocate_application_number

        request_number = await allocate_application_number(db)

        new_registration = Registrations(
            business_name=data.business_name,
            merchant_name=data.merchant_name,
            phone=data.phone,
            governorate=data.governorate,
            area=data.area,
            business_type=data.business_type,
            image_key=image_key,
            notes=data.notes or "",
            extra_fields=dumps_extra_fields(data.extra_fields),
            status="pending",
            membership_number=None,
            request_number=request_number,
            membership_status=None,
            approved_at=None,
            whatsapp_registration_sent=False,
            whatsapp_approval_sent=False,
            whatsapp_last_attempt="",
            whatsapp_status="none",
            user_id="public",
        )

        db.add(new_registration)
        await db.commit()
        await db.refresh(new_registration)

        logger.info(f"New public registration: {new_registration.id} - {data.business_name} - {request_number}")

        return PublicRegistrationResponse(
            success=True,
            message="تم إرسال طلب الانضمام بنجاح. سيتم مراجعته والتواصل معك عبر واتساب.",
            request_number=request_number,
        )

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in public registration: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="حدث خطأ أثناء إرسال الطلب. يرجى المحاولة لاحقاً.")
