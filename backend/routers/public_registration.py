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
MAX_IMAGE_BYTES = s3store.MAX_REGISTRATION_IMAGE_BYTES


def _safe_registration_key(object_key: str) -> str:
    key = s3store.normalize_business_key(object_key)
    if not SAFE_KEY.match(key):
        raise HTTPException(status_code=400, detail="مسار الملف غير صالح")
    return key


async def _begin_reg_perf(request: Request) -> str:
    """Assign request id (+ opt-in stage timing) before get_db."""
    return reg_perf.enable_from_request(request)


async def _cleanup_uploaded_object(image_key: Optional[str], reason: str) -> None:
    """Best-effort delete of a just-uploaded object after a failed registration."""
    if not image_key or image_key == s3store.MANUAL_ENTRY_KEY:
        return
    try:
        key = s3store.validate_registration_image_key(image_key)
    except s3store.SupabaseStorageError:
        return
    if key == s3store.MANUAL_ENTRY_KEY:
        return
    try:
        with reg_perf.stage("upload_cleanup"):
            ok = await s3store.delete_object(key)
        rid = reg_perf.request_id() or "-"
        logger.info(
            "REG_TIMING rid=%s stage=upload_cleanup ok=%s reason=%s",
            rid,
            ok,
            reason,
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("upload cleanup failed rid=%s: %s", reg_perf.request_id(), e)


class UploadUrlRequest(BaseModel):
    bucket_name: str
    object_key: str


class UploadUrlResponse(BaseModel):
    upload_url: str
    object_key: str = ""
    expires_at: str = ""


class PresignUploadRequest(BaseModel):
    filename: str
    content_type: Optional[str] = None
    size_bytes: Optional[int] = None

    @validator("filename")
    def filename_required(cls, v):
        if not v or not str(v).strip():
            raise ValueError("اسم الملف مطلوب")
        return str(v).strip()


class PresignUploadResponse(BaseModel):
    upload_url: str
    object_key: str
    token: str = ""
    content_type: str = ""
    max_bytes: int = MAX_IMAGE_BYTES
    expires_in_seconds: int = 120


class CleanupUploadRequest(BaseModel):
    object_key: str


@router.post("/presign-upload", response_model=PresignUploadResponse)
async def presign_registration_upload(
    data: PresignUploadRequest,
    request: Request,
    _rid: str = Depends(_begin_reg_perf),
):
    """Generate a short-lived Supabase signed upload URL (service role stays on backend).

    Frontend PUTs the file directly to ``upload_url``, then submits ``object_key``
    as ``image_key`` on ``POST /register``.
    """
    t0 = time.perf_counter()
    try:
        with reg_perf.stage("presign_validate"):
            ext, ctype = s3store.validate_registration_image_meta(
                filename=data.filename,
                content_type=data.content_type,
                size_bytes=data.size_bytes,
            )
            object_key = s3store.make_unique_registration_object_key(f"img{ext}")
        with reg_perf.stage("presign_generation"):
            upload_url, object_key, token = await s3store.create_signed_upload_url(
                object_key, upsert=False
            )
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        reg_perf.record("handler_total", elapsed_ms)
        logger.info(
            "REG_TIMING rid=%s stage=presign_generation ms=%.2f object_key_len=%s",
            reg_perf.request_id() or "-",
            elapsed_ms,
            len(object_key),
        )
        body = PresignUploadResponse(
            upload_url=upload_url,
            object_key=object_key,
            token=token,
            content_type=ctype,
            max_bytes=MAX_IMAGE_BYTES,
            expires_in_seconds=120,
        )
        headers = reg_perf.apply_response_headers({})
        return JSONResponse(content=body.dict(), headers=headers)
    except s3store.SupabaseStorageError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error("presign-upload failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="فشل إنشاء رابط الرفع")


@router.post("/cleanup-upload")
async def cleanup_registration_upload(
    data: CleanupUploadRequest,
    request: Request,
    _rid: str = Depends(_begin_reg_perf),
):
    """Delete an orphaned registration object after a failed client-side submit."""
    try:
        key = s3store.validate_registration_image_key(data.object_key)
    except s3store.SupabaseStorageError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if key == s3store.MANUAL_ENTRY_KEY:
        raise HTTPException(status_code=400, detail="مسار الملف غير صالح")
    with reg_perf.stage("upload_cleanup"):
        ok = await s3store.delete_object(key)
    headers = reg_perf.apply_response_headers({})
    return JSONResponse(content={"success": bool(ok), "object_key": key}, headers=headers)


@router.post("/upload-url", response_model=UploadUrlResponse)
async def get_public_upload_url(data: UploadUrlRequest, request: Request):
    """Legacy: return backend proxy upload URL (prefer POST /presign-upload)."""
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
    _rid: str = Depends(_begin_reg_perf),
):
    """Legacy proxy upload (PUT) → Supabase Storage. Prefer direct signed upload."""
    t_handler = time.perf_counter()
    safe_key = _safe_registration_key(object_key)
    try:
        with reg_perf.stage("upload_read_body"):
            content = await request.body()
        if not content:
            raise HTTPException(status_code=400, detail="الملف فارغ")
        if len(content) > MAX_IMAGE_BYTES:
            raise HTTPException(status_code=400, detail="الحد الأقصى 5MB")
        content_type = (request.headers.get("content-type") or "").split(";")[0].strip().lower()
        if content_type == "image/jpg":
            content_type = "image/jpeg"
        if content_type and content_type not in s3store.ALLOWED_REGISTRATION_IMAGE_TYPES:
            raise HTTPException(status_code=400, detail="صيغة الملف غير مدعومة")
        content_len = len(content)
        with reg_perf.stage("upload_supabase_storage"):
            await s3store.upload_bytes(
                safe_key, content, content_type=content_type or None, upsert=False
            )
        with reg_perf.stage("response_serialization"):
            body = {"success": True, "object_key": safe_key, "size": content_len}
        reg_perf.record("handler_total", (time.perf_counter() - t_handler) * 1000.0)
        headers = reg_perf.apply_response_headers({})
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
    """Legacy multipart upload → Supabase Storage. Prefer direct signed upload."""
    safe_key = _safe_registration_key(object_key)
    try:
        content = await file.read()
        if not content:
            raise HTTPException(status_code=400, detail="الملف فارغ")
        if len(content) > MAX_IMAGE_BYTES:
            raise HTTPException(status_code=400, detail="الحد الأقصى 5MB")
        ctype = (file.content_type or "").split(";")[0].strip().lower()
        if ctype == "image/jpg":
            ctype = "image/jpeg"
        if ctype and ctype not in s3store.ALLOWED_REGISTRATION_IMAGE_TYPES:
            raise HTTPException(status_code=400, detail="صيغة الملف غير مدعومة")
        await s3store.upload_bytes(
            safe_key,
            content,
            content_type=ctype or None,
            upsert=False,
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
    with reg_perf.stage("response_serialization"):
        payload = body.dict()
    total_ms = (time.perf_counter() - t_handler) * 1000.0
    reg_perf.record("handler_total", total_ms)
    logger.info(
        "REG_TIMING rid=%s stage=db_transaction_total ms=%.2f success=%s",
        reg_perf.request_id() or "-",
        total_ms,
        body.success,
    )
    headers = reg_perf.apply_response_headers({})
    if headers:
        return JSONResponse(content=payload, headers=headers)
    return body


@router.post("/register", response_model=PublicRegistrationResponse)
async def public_register(
    data: PublicRegistrationRequest,
    request: Request,
    _rid: str = Depends(_begin_reg_perf),
    db: AsyncSession = Depends(get_db),
):
    """Public registration — no login required."""
    t_handler = time.perf_counter()
    image_key_for_cleanup: Optional[str] = None
    try:
        from sqlalchemy.exc import IntegrityError

        from services.extra_fields import dumps_extra_fields
        from services.membership_numbers import (
            allocate_application_number,
            lock_phone_check_and_allocate,
        )
        from services.panel_auth import ensure_schema

        # Fast no-op after startup; kept as a safety net.
        with reg_perf.stage("ensure_schema"):
            await ensure_schema()

        idem_key = data.idempotency_key or (request.headers.get("X-Idempotency-Key") or "").strip() or None
        if idem_key and not re.match(r"^[A-Za-z0-9._\-]+$", idem_key):
            idem_key = None

        try:
            with reg_perf.stage("image_key_validate"):
                image_key = s3store.validate_registration_image_key(data.image_key or "manual_entry")
        except s3store.SupabaseStorageError as e:
            raise HTTPException(status_code=400, detail=str(e))
        if image_key != s3store.MANUAL_ENTRY_KEY:
            image_key_for_cleanup = image_key

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

        # First real pool checkout / TCP if session was lazy — timed separately.
        with reg_perf.stage("db_connection_acquisition"):
            try:
                bind = await db.connection()
            except Exception:
                bind = None

        combined = {}
        if bind is not None:
            try:
                combined = await lock_phone_check_and_allocate(db, data.phone)
            except Exception as comb_err:
                logger.debug("combined lock/phone/allocate skipped: %s", comb_err)
                combined = {}

        if combined:
            if combined.get("existing_id") is not None:
                extra_raw = combined.get("existing_extra_fields") or ""
                if idem_key and f'"_idempotency_key": "{idem_key}"' in extra_raw:
                    reg_perf.record("application_number_generation", 0.0)
                    reg_perf.record("database_insert_commit", 0.0)
                    reg_perf.record("idempotency_replay", 0.0)
                    # Same payload replay — do NOT delete image_key (it belongs to the row).
                    image_key_for_cleanup = None
                    return _register_response(
                        PublicRegistrationResponse(
                            success=True,
                            message=_SUCCESS_MSG,
                            request_number=combined.get("existing_request_number"),
                        ),
                        t_handler,
                    )
                await _cleanup_uploaded_object(image_key_for_cleanup, "duplicate_phone")
                image_key_for_cleanup = None
                raise HTTPException(
                    status_code=409,
                    detail="يوجد طلب مسجل مسبقاً بهذا الرقم. يرجى الانتظار حتى تتم مراجعة طلبك.",
                )
            request_number = combined.get("request_number")
        else:
            # Non-Postgres / fallback: advisory lock + phone check + allocate separately.
            try:
                if bind is not None and bind.dialect.name == "postgresql":
                    from sqlalchemy import text as sql_text

                    with reg_perf.stage("advisory_lock"):
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
                    extra_raw = row.extra_fields or ""
                    if idem_key and f'"_idempotency_key": "{idem_key}"' in extra_raw:
                        reg_perf.record("application_number_generation", 0.0)
                        reg_perf.record("database_insert_commit", 0.0)
                        reg_perf.record("idempotency_replay", 0.0)
                        # Same payload replay — keep existing image_key.
                        image_key_for_cleanup = None
                        return _register_response(
                            PublicRegistrationResponse(
                                success=True,
                                message=_SUCCESS_MSG,
                                request_number=row.request_number,
                            ),
                            t_handler,
                        )
                    await _cleanup_uploaded_object(image_key_for_cleanup, "duplicate_phone")
                    image_key_for_cleanup = None
                    raise HTTPException(
                        status_code=409,
                        detail="يوجد طلب مسجل مسبقاً بهذا الرقم. يرجى الانتظار حتى تتم مراجعة طلبك.",
                    )
            request_number = None

        last_err: Optional[Exception] = None
        for attempt in range(5):
            try:
                with reg_perf.stage("application_number_generation"):
                    if not request_number:
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
                image_key_for_cleanup = None  # owned by successful row
                break
            except IntegrityError as ie:
                last_err = ie
                await db.rollback()
                logger.warning("public_register IntegrityError attempt=%s: %s", attempt, ie)
                # Rare collision: counter rolled back with the txn; next allocate retries.
                request_number = None
                continue

        if last_err is not None or not request_number:
            await _cleanup_uploaded_object(image_key_for_cleanup, "insert_failed")
            image_key_for_cleanup = None
            raise HTTPException(
                status_code=500,
                detail="حدث خطأ أثناء إرسال الطلب. يرجى المحاولة لاحقاً.",
            )

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
        await _cleanup_uploaded_object(image_key_for_cleanup, "unexpected_error")
        logger.error(f"Error in public registration: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="حدث خطأ أثناء إرسال الطلب. يرجى المحاولة لاحقاً.")
