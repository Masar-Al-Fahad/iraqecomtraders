"""Supabase Storage helper (bucket: uploads). Replaces local backend/uploads filesystem."""
from __future__ import annotations

import logging
import mimetypes
import re
import uuid
from datetime import datetime, timezone
from typing import Optional, Tuple
from urllib.parse import quote

import httpx

from core.config import settings

logger = logging.getLogger(__name__)

DEFAULT_BUCKET = "uploads"
FINANCIAL_PRIVATE_BUCKET = "financial-private"
MAX_REGISTRATION_IMAGE_BYTES = 5 * 1024 * 1024
ALLOWED_REGISTRATION_IMAGE_TYPES = frozenset(
    {"image/jpeg", "image/jpg", "image/png", "image/webp"}
)
ALLOWED_REGISTRATION_IMAGE_EXTS = frozenset({".jpg", ".jpeg", ".png", ".webp"})
SAFE_REGISTRATION_KEY = re.compile(r"^registrations/[A-Za-z0-9._\-]+$")
MANUAL_ENTRY_KEY = "manual_entry"


class SupabaseStorageError(RuntimeError):
    pass


def _base_url() -> str:
    url = (getattr(settings, "supabase_url", None) or "").strip().rstrip("/")
    if not url:
        raise SupabaseStorageError(
            "SUPABASE_URL غير مضبوط. أضفه في backend/.env مثل "
            "https://YOUR_PROJECT_REF.supabase.co"
        )
    return url


def _api_key() -> str:
    key = (
        (getattr(settings, "supabase_service_role_key", None) or "").strip()
        or (getattr(settings, "supabase_anon_key", None) or "").strip()
    )
    if not key:
        raise SupabaseStorageError(
            "SUPABASE_SERVICE_ROLE_KEY (أو SUPABASE_ANON_KEY) غير مضبوط في backend/.env"
        )
    return key


def bucket_name() -> str:
    return (getattr(settings, "supabase_storage_bucket", None) or DEFAULT_BUCKET).strip() or DEFAULT_BUCKET


def normalize_business_key(object_key: str) -> str:
    key = (object_key or "").replace("\\", "/").lstrip("/")
    if key.startswith("business-images/"):
        key = key[len("business-images/") :]
    if not key.startswith("registrations/"):
        key = f"registrations/{key}"
    return key


def normalize_brand_key(object_key: str) -> str:
    key = (object_key or "").replace("\\", "/").lstrip("/")
    if key.startswith("brand/"):
        return key
    return f"brand/{key}"


def public_object_url(object_path: str) -> str:
    """Public URL for an object inside the uploads bucket."""
    path = object_path.replace("\\", "/").lstrip("/")
    # Encode each segment but keep slashes
    encoded = "/".join(quote(seg, safe="") for seg in path.split("/"))
    return f"{_base_url()}/storage/v1/object/public/{bucket_name()}/{encoded}"


def _headers(content_type: Optional[str] = None, upsert: bool = False) -> dict:
    h = {
        "Authorization": f"Bearer {_api_key()}",
        "apikey": _api_key(),
    }
    if content_type:
        h["Content-Type"] = content_type
    if upsert:
        h["x-upsert"] = "true"
    return h


_http_client: Optional[httpx.AsyncClient] = None


def _shared_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.AsyncClient(timeout=60.0, follow_redirects=True)
    return _http_client


async def upload_bytes(
    object_path: str,
    content: bytes,
    *,
    content_type: Optional[str] = None,
    upsert: bool = True,
) -> str:
    """Upload bytes to bucket. Returns storage object path (not URL)."""
    path = object_path.replace("\\", "/").lstrip("/")
    if not content:
        raise SupabaseStorageError("الملف فارغ")
    ctype = content_type or mimetypes.guess_type(path)[0] or "application/octet-stream"
    url = f"{_base_url()}/storage/v1/object/{bucket_name()}/{path}"
    client = _shared_client()
    resp = await client.post(url, content=content, headers=_headers(ctype, upsert=upsert))
    if resp.status_code in (200, 201):
        return path
    # Some gateways prefer PUT for upsert
    if resp.status_code in (400, 409, 405):
        resp = await client.put(url, content=content, headers=_headers(ctype, upsert=True))
        if resp.status_code in (200, 201):
            return path
    raise SupabaseStorageError(
        f"فشل رفع الملف إلى Supabase Storage ({resp.status_code}): {resp.text[:300]}"
    )


async def ensure_financial_private_bucket() -> None:
    """Create the dedicated non-public financial bucket when absent."""
    client = _shared_client()
    url = f"{_base_url()}/storage/v1/bucket"
    headers = {**_headers(), "Content-Type": "application/json"}
    resp = await client.post(
        url,
        headers=headers,
        json={
            "id": FINANCIAL_PRIVATE_BUCKET,
            "name": FINANCIAL_PRIVATE_BUCKET,
            "public": False,
            "file_size_limit": 10 * 1024 * 1024,
            "allowed_mime_types": [
                "application/pdf", "image/jpeg", "image/png", "image/webp"
            ],
        },
    )
    if resp.status_code not in (200, 201, 409):
        # Existing buckets may return 400 with a duplicate message.
        if "already exists" not in (resp.text or "").lower():
            raise SupabaseStorageError(
                f"تعذر تجهيز مخزن المستندات الخاصة ({resp.status_code})"
            )


async def upload_private_financial_bytes(
    object_path: str, content: bytes, *, content_type: str
) -> str:
    await ensure_financial_private_bucket()
    path = object_path.replace("\\", "/").lstrip("/")
    url = (
        f"{_base_url()}/storage/v1/object/"
        f"{FINANCIAL_PRIVATE_BUCKET}/{path}"
    )
    resp = await _shared_client().post(
        url, content=content, headers=_headers(content_type, upsert=False)
    )
    if resp.status_code not in (200, 201):
        raise SupabaseStorageError(
            f"فشل حفظ المستند الخاص ({resp.status_code})"
        )
    return path


async def download_private_financial_bytes(object_path: str) -> Tuple[bytes, str]:
    path = object_path.replace("\\", "/").lstrip("/")
    encoded = "/".join(quote(seg, safe="") for seg in path.split("/"))
    url = (
        f"{_base_url()}/storage/v1/object/"
        f"{FINANCIAL_PRIVATE_BUCKET}/{encoded}"
    )
    resp = await _shared_client().get(url, headers=_headers())
    if resp.status_code != 200:
        raise SupabaseStorageError("المستند غير موجود أو غير متاح")
    return (
        resp.content,
        resp.headers.get("content-type")
        or mimetypes.guess_type(path)[0]
        or "application/octet-stream",
    )


async def download_bytes(object_path: str) -> Tuple[bytes, str]:
    """Download object bytes. Returns (content, content_type)."""
    path = object_path.replace("\\", "/").lstrip("/")
    # Try public URL first (works for public buckets)
    public_url = public_object_url(path)
    async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
        resp = await client.get(public_url)
        if resp.status_code == 200:
            ctype = resp.headers.get("content-type") or mimetypes.guess_type(path)[0] or "application/octet-stream"
            return resp.content, ctype
        # Authenticated fallback
        auth_url = f"{_base_url()}/storage/v1/object/{bucket_name()}/{path}"
        resp = await client.get(auth_url, headers=_headers())
        if resp.status_code == 200:
            ctype = resp.headers.get("content-type") or mimetypes.guess_type(path)[0] or "application/octet-stream"
            return resp.content, ctype
        raise SupabaseStorageError(
            f"الملف غير موجود في Storage ({resp.status_code}): {path}"
        )


async def object_exists(object_path: str) -> bool:
    try:
        await download_bytes(object_path)
        return True
    except Exception:
        return False


async def delete_object(object_path: str) -> bool:
    """Delete an object from the uploads bucket. Returns True if deleted or already gone."""
    path = object_path.replace("\\", "/").lstrip("/")
    if not path:
        return False
    client = _shared_client()
    headers = {**_headers(), "Content-Type": "application/json"}
    # Official Storage API: DELETE /object/{bucket} with JSON body {prefixes:[...]}
    batch_url = f"{_base_url()}/storage/v1/object/{bucket_name()}"
    resp = await client.request(
        "DELETE",
        batch_url,
        headers=headers,
        json={"prefixes": [path]},
    )
    if resp.status_code in (200, 204):
        return True
    # Fallback: path-style DELETE (some gateways)
    encoded = "/".join(quote(seg, safe="") for seg in path.split("/"))
    path_url = f"{_base_url()}/storage/v1/object/{bucket_name()}/{encoded}"
    resp2 = await client.delete(path_url, headers=_headers())
    if resp2.status_code in (200, 204, 404):
        return True
    if resp.status_code == 404:
        return True
    logger.warning(
        "Supabase delete failed batch=%s path=%s for %s: %s | %s",
        resp.status_code,
        resp2.status_code,
        path,
        (resp.text or "")[:120],
        (resp2.text or "")[:120],
    )
    return False


def validate_registration_image_meta(
    *,
    filename: str,
    content_type: Optional[str],
    size_bytes: Optional[int],
) -> Tuple[str, str]:
    """Validate client-declared image metadata. Returns (safe_ext, normalized_content_type)."""
    name = (filename or "").strip()
    if not name:
        raise SupabaseStorageError("اسم الملف مطلوب")
    # basename only
    name = name.replace("\\", "/").split("/")[-1]
    lower = name.lower()
    ext = ""
    if "." in lower:
        ext = "." + lower.rsplit(".", 1)[-1]
    if ext not in ALLOWED_REGISTRATION_IMAGE_EXTS:
        raise SupabaseStorageError("صيغة الملف غير مدعومة")

    ctype = (content_type or "").strip().lower()
    if not ctype:
        ctype = mimetypes.guess_type(f"x{ext}")[0] or "application/octet-stream"
    if ctype == "image/jpg":
        ctype = "image/jpeg"
    if ctype not in ALLOWED_REGISTRATION_IMAGE_TYPES:
        raise SupabaseStorageError("صيغة الملف غير مدعومة")

    if size_bytes is not None:
        if size_bytes < 1:
            raise SupabaseStorageError("الملف فارغ")
        if size_bytes > MAX_REGISTRATION_IMAGE_BYTES:
            raise SupabaseStorageError("الحد الأقصى 5MB")
    return ext, ctype


def make_unique_registration_object_key(filename: str) -> str:
    """Unique registrations/ key (UUID + timestamp) — never overwrite existing objects."""
    ext, _ = validate_registration_image_meta(
        filename=filename, content_type=None, size_bytes=None
    )
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    return f"registrations/{stamp}_{uuid.uuid4().hex}{ext}"


def validate_registration_image_key(image_key: str) -> str:
    """Accept manual_entry or a safe registrations/ object path."""
    key = (image_key or "").strip() or MANUAL_ENTRY_KEY
    if key == MANUAL_ENTRY_KEY:
        return key
    key = normalize_business_key(key)
    if not SAFE_REGISTRATION_KEY.match(key):
        raise SupabaseStorageError("مسار الملف غير صالح")
    return key


async def create_signed_upload_url(
    object_path: str,
    *,
    upsert: bool = False,
) -> Tuple[str, str, str]:
    """Create a short-lived signed upload URL via Supabase Storage API.

    Returns (full_upload_url, object_path, token).
    Client PUTs the file directly to full_upload_url (no service role on frontend).
    """
    path = object_path.replace("\\", "/").lstrip("/")
    if not path:
        raise SupabaseStorageError("مسار الملف مطلوب")
    # Encode path segments for the sign endpoint
    encoded = "/".join(quote(seg, safe="") for seg in path.split("/"))
    sign_url = f"{_base_url()}/storage/v1/object/upload/sign/{bucket_name()}/{encoded}"
    headers = _headers()
    headers["x-upsert"] = "true" if upsert else "false"
    client = _shared_client()
    resp = await client.post(sign_url, headers=headers)
    if resp.status_code not in (200, 201):
        raise SupabaseStorageError(
            f"فشل إنشاء رابط الرفع ({resp.status_code}): {(resp.text or '')[:300]}"
        )
    data = resp.json() if resp.content else {}
    relative = (data.get("url") or "").strip()
    token = (data.get("token") or "").strip()
    if not relative:
        raise SupabaseStorageError("لم يُرجع Supabase رابط رفع موقّع")
    if relative.startswith("http://") or relative.startswith("https://"):
        full = relative
    else:
        # Typical: /object/upload/sign/uploads/registrations/...?token=...
        if not relative.startswith("/"):
            relative = "/" + relative
        if relative.startswith("/storage/v1/"):
            full = f"{_base_url()}{relative}"
        else:
            full = f"{_base_url()}/storage/v1{relative}"
    # Ensure token is present on the URL when returned separately
    if token and "token=" not in full:
        sep = "&" if "?" in full else "?"
        full = f"{full}{sep}token={quote(token, safe='')}"
    return full, path, token


def configured() -> bool:
    try:
        _base_url()
        _api_key()
        return True
    except SupabaseStorageError:
        return False
