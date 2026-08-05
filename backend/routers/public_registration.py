"""Public registration + Supabase Storage uploads — no authentication required."""
import logging
import re
import time
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.database import get_db
from models.registrations import Registrations
from services import reg_perf
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
    reg_perf.enable_from_request(request)
    safe_key = _safe_registration_key(object_key)
    try:
        with reg_perf.stage("upload_read_body"):
            content = await request.body()
        if not content:
            raise HTTPException(status_code=400, detail="الملف فارغ")
        if len(content) > 5 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="الحد الأقصى 5MB")
        with reg_perf.stage("upload_supabase_storage"):
            await s3store.upload_bytes(safe_key, content, upsert=True)
        body = {"success": True, "object_key": safe_key, "size": len(content)}
        headers = {}
        perf_hdr = reg_perf.response_header_value()
        if perf_hdr:
            headers[reg_perf.HEADER_RESPONSE] = perf_hdr
        return JSONResponse(content=body, headers=headers)
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
    # Optional client key to make double-submit retries idempotent (additive; ignored if absent)
    idempotency_key: Optional[str] = None

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

    @validator("idempotency_key")
    def clean_idempotency_key(cls, v):
        if v is None:
            return None
        key = str(v).strip()
        if not key:
            return None
        if len(key) > 64 or not re.match(r"^[A-Za-z0-9._\-]+$", key):
            raise ValueError("مفتاح التكرار غير صالح")
        return key


class PublicRegistrationResponse(BaseModel):
    success: bool
    message: str
    request_number: Optional[str] = None


_SUCCESS_MSG = "تم إرسال طلب الانضمام بنجاح. سيتم مراجعته والتواصل معك عبر واتساب."


def _register_response(body: PublicRegistrationResponse, t_handler: float):
    reg_perf.record("handler_total", (time.perf_counter() - t_handler) * 1000.0)
    headers = {}
    perf_hdr = reg_perf.response_header_value()
    if perf_hdr:
        headers[reg_perf.HEADER_RESPONSE] = perf_hdr
        logger.info("REG_PERF register %s", perf_hdr)
    if headers:
        return JSONResponse(content=body.dict(), headers=headers)
    return body


@router.post("/register", response_model=PublicRegistrationResponse)
async def public_register(
    data: PublicRegistrationRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Public registration — no login required."""
    reg_perf.enable_from_request(request)
    t_handler = time.perf_counter()
    try:
        from sqlalchemy.exc import IntegrityError

        from services.extra_fields import dumps_extra_fields
        from services.membership_numbers import allocate_application_number
        from services.panel_auth import ensure_schema

        # Fast no-op after startup; kept as a safety net.
        with reg_perf.stage("ensure_schema"):
            await ensure_schema()

        idem_key = data.idempotency_key or (request.headers.get("X-Idempotency-Key") or "").strip() or None
        if idem_key and not re.match(r"^[A-Za-z0-9._\-]+$", idem_key):
            idem_key = None

        # Serialize concurrent submits for the same phone (Postgres).
        try:
            bind = await db.connection()
            if bind.dialect.name == "postgresql":
                from sqlalchemy import text as sql_text

                await db.execute(
                    sql_text("SELECT pg_advisory_xact_lock(hashtext(:phone))"),
                    {"phone": data.phone},
                )
        except Exception as lock_err:
            logger.debug("advisory lock skipped: %s", lock_err)

        with reg_perf.stage("phone_uniqueness_check"):
            existing = await db.execute(
                select(
                    Registrations.id,
                    Registrations.request_number,
                    Registrations.extra_fields,
                ).where(
                    Registrations.phone == data.phone,
                    Registrations.status != "rejected",
                ).limit(1)
            )
            row = existing.first()
            if row is not None:
                # Same idempotency key → safe replay (double-submit / retry).
                extra_raw = row.extra_fields or ""
                if idem_key and f'"_idempotency_key": "{idem_key}"' in extra_raw:
                    reg_perf.record("membership_number_generation", 0.0)
                    reg_perf.record("audit_logging", 0.0)
                    reg_perf.record("application_number_generation", 0.0)
                    reg_perf.record("database_insert_commit", 0.0)
                    reg_perf.record("followup_refresh", 0.0)
                    reg_perf.record("idempotency_replay", 0.0)
                    return _register_response(
                        PublicRegistrationResponse(
                            success=True,
                            message=_SUCCESS_MSG,
                            request_number=row.request_number,
                        ),
                        t_handler,
                    )
                raise HTTPException(
                    status_code=409,
                    detail="يوجد طلب مسجل مسبقاً بهذا الرقم. يرجى الانتظار حتى تتم مراجعة طلبك.",
                )

        image_key = data.image_key or "manual_entry"
        import json as _json

        with reg_perf.stage("payload_prepare_orm"):
            extra_obj = _json.loads(dumps_extra_fields(data.extra_fields))
            if idem_key:
                extra_obj["_idempotency_key"] = idem_key
            extra_fields_json = _json.dumps(extra_obj, ensure_ascii=False)

        # Membership numbers are allocated on admin approval, not at public submit.
        reg_perf.record("membership_number_generation", 0.0)
        # Public register does not write audit_logs (kept off the critical path).
        reg_perf.record("audit_logging", 0.0)
        reg_perf.record("followup_refresh", 0.0)

        request_number: Optional[str] = None
        last_err: Optional[Exception] = None
        for attempt in range(5):
            try:
                with reg_perf.stage("application_number_generation"):
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
                    extra_fields=extra_fields_json,
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
                with reg_perf.stage("database_insert_commit"):
                    await db.commit()
                last_err = None
                break
            except IntegrityError as ie:
                last_err = ie
                await db.rollback()
                logger.warning("public_register IntegrityError attempt=%s: %s", attempt, ie)
                # Rare collision: counter rolled back with the txn; next allocate retries.
                continue

        if last_err is not None or not request_number:
            raise HTTPException(
                status_code=500,
                detail="حدث خطأ أثناء إرسال الطلب. يرجى المحاولة لاحقاً.",
            )

        # Return application code immediately — no refresh / follow-up queries.
        logger.info("New public registration: %s - %s", data.business_name, request_number)

        return _register_response(
            PublicRegistrationResponse(
                success=True,
                message=_SUCCESS_MSG,
                request_number=request_number,
            ),
            t_handler,
        )

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in public registration: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="حدث خطأ أثناء إرسال الطلب. يرجى المحاولة لاحقاً.")
