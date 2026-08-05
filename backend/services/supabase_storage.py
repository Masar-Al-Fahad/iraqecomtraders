"""Supabase Storage helper (bucket: uploads). Replaces local backend/uploads filesystem."""
from __future__ import annotations

import logging
import mimetypes
from typing import Optional, Tuple
from urllib.parse import quote

import httpx

from core.config import settings

logger = logging.getLogger(__name__)

DEFAULT_BUCKET = "uploads"


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


def configured() -> bool:
    try:
        _base_url()
        _api_key()
        return True
    except SupabaseStorageError:
        return False
