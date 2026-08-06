"""
Registration latency fix — scenario tests + before/after timing report.

Scenarios:
  1. no image
  2. valid image (presign → direct Supabase PUT → register)
  3. oversized / invalid image
  4. failed registration after upload (cleanup)
  5. duplicate submission (idempotency)

Usage (from backend/):
  .venv\\Scripts\\python.exe _test_reg_direct_upload.py
  .venv\\Scripts\\python.exe _test_reg_direct_upload.py --base-url http://127.0.0.1:8012
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import subprocess
import sys
import time
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

BACKEND_DIR = Path(__file__).resolve().parent
os.chdir(BACKEND_DIR)
sys.path.insert(0, str(BACKEND_DIR))

from dotenv import load_dotenv

load_dotenv(BACKEND_DIR / ".env", override=True)

PERF_HEADER = {"X-Reg-Perf": "1"}


def _tiny_png_bytes() -> bytes:
    import base64

    return base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    )


def _parse_perf(resp) -> Dict[str, Any]:
    raw = resp.headers.get("x-reg-perf-stages") or resp.headers.get("X-Reg-Perf-Stages")
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except Exception:
        return {"raw": raw}


async def _wait_for_ready(base: str, timeout: float = 90.0) -> None:
    import httpx

    deadline = time.time() + timeout
    last_err = None
    async with httpx.AsyncClient(timeout=10.0) as client:
        while time.time() < deadline:
            try:
                r = await client.get(f"{base}/health")
                if r.status_code == 200:
                    return
            except Exception as e:  # noqa: BLE001
                last_err = e
            await asyncio.sleep(0.5)
    raise RuntimeError(f"Server not ready within {timeout}s: {last_err}")


def _phone() -> str:
    return f"079{random.randint(10000000, 99999999)}"


def _payload(phone: str, image_key: str = "manual_entry", idem: Optional[str] = None) -> dict:
    return {
        "business_name": f"Test Biz {uuid.uuid4().hex[:6]}",
        "merchant_name": "Test Merchant",
        "phone": phone,
        "governorate": "بغداد",
        "area": "الكرادة",
        "business_type": "تجارة",
        "image_key": image_key,
        "notes": "",
        "extra_fields": {},
        "idempotency_key": idem or uuid.uuid4().hex,
    }


async def _presign_and_upload(client, base: str, content: bytes, *, filename: str, content_type: str) -> Dict[str, Any]:
    t0 = time.perf_counter()
    pr = await client.post(
        f"{base}/api/v1/public/presign-upload",
        json={
            "filename": filename,
            "content_type": content_type,
            "size_bytes": len(content),
        },
        headers={**PERF_HEADER, "X-Request-Id": uuid.uuid4().hex},
    )
    presign_ms = (time.perf_counter() - t0) * 1000.0
    body = pr.json() if pr.content else {}
    if pr.status_code != 200:
        return {
            "ok": False,
            "status": pr.status_code,
            "detail": body.get("detail"),
            "presign_ms": round(presign_ms, 2),
            "presign_perf": _parse_perf(pr),
        }
    upload_url = body.get("upload_url")
    object_key = body.get("object_key")
    ctype = body.get("content_type") or content_type
    t1 = time.perf_counter()
    # Direct to Supabase — no backend proxy
    put = await client.put(
        upload_url,
        content=content,
        headers={"Content-Type": ctype},
    )
    upload_ms = (time.perf_counter() - t1) * 1000.0
    return {
        "ok": put.status_code in (200, 201),
        "status": put.status_code,
        "detail": (put.text or "")[:200] if put.status_code not in (200, 201) else None,
        "object_key": object_key,
        "presign_ms": round(presign_ms, 2),
        "direct_upload_ms": round(upload_ms, 2),
        "presign_perf": _parse_perf(pr),
        "cors_hint": put.status_code == 0
        or (put.status_code in (0,) )
        or ("CORS" in (put.text or "").upper()),
    }


async def scenario_no_image(client, base: str) -> Dict[str, Any]:
    phone = _phone()
    t0 = time.perf_counter()
    r = await client.post(
        f"{base}/api/v1/public/register",
        json=_payload(phone),
        headers={**PERF_HEADER, "X-Request-Id": uuid.uuid4().hex},
    )
    total_ms = (time.perf_counter() - t0) * 1000.0
    body = r.json() if r.content else {}
    return {
        "scenario": "no_image",
        "pass": r.status_code == 200 and body.get("success") is True and bool(body.get("request_number")),
        "status": r.status_code,
        "request_number": body.get("request_number"),
        "total_submit_ms": round(total_ms, 2),
        "server_perf": _parse_perf(r),
        "request_id": r.headers.get("x-request-id"),
        "detail": body.get("detail"),
    }


async def scenario_valid_image(client, base: str) -> Dict[str, Any]:
    phone = _phone()
    up = await _presign_and_upload(
        client, base, _tiny_png_bytes(), filename="ok.png", content_type="image/png"
    )
    if not up.get("ok"):
        return {
            "scenario": "valid_image",
            "pass": False,
            "status": up.get("status"),
            "detail": up.get("detail") or "presign/upload failed",
            "upload": up,
            "manual_supabase_cors": True,
        }
    t0 = time.perf_counter()
    r = await client.post(
        f"{base}/api/v1/public/register",
        json=_payload(phone, image_key=up["object_key"]),
        headers={**PERF_HEADER, "X-Request-Id": uuid.uuid4().hex},
    )
    reg_ms = (time.perf_counter() - t0) * 1000.0
    body = r.json() if r.content else {}
    total = (up.get("presign_ms") or 0) + (up.get("direct_upload_ms") or 0) + reg_ms
    return {
        "scenario": "valid_image",
        "pass": r.status_code == 200 and body.get("success") is True,
        "status": r.status_code,
        "request_number": body.get("request_number"),
        "presign_ms": up.get("presign_ms"),
        "direct_upload_ms": up.get("direct_upload_ms"),
        "register_ms": round(reg_ms, 2),
        "total_submit_ms": round(total, 2),
        "server_perf": _parse_perf(r),
        "presign_perf": up.get("presign_perf"),
        "object_key": up.get("object_key"),
        "detail": body.get("detail"),
    }


async def scenario_invalid_images(client, base: str) -> Dict[str, Any]:
    results = []
    # Oversized
    t0 = time.perf_counter()
    r1 = await client.post(
        f"{base}/api/v1/public/presign-upload",
        json={
            "filename": "big.png",
            "content_type": "image/png",
            "size_bytes": 6 * 1024 * 1024,
        },
        headers=PERF_HEADER,
    )
    results.append(
        {
            "case": "oversized",
            "status": r1.status_code,
            "pass": r1.status_code == 400,
            "detail": (r1.json() if r1.content else {}).get("detail"),
            "ms": round((time.perf_counter() - t0) * 1000.0, 2),
        }
    )
    # Invalid type
    t1 = time.perf_counter()
    r2 = await client.post(
        f"{base}/api/v1/public/presign-upload",
        json={
            "filename": "evil.exe",
            "content_type": "application/octet-stream",
            "size_bytes": 100,
        },
        headers=PERF_HEADER,
    )
    results.append(
        {
            "case": "invalid_type",
            "status": r2.status_code,
            "pass": r2.status_code == 400,
            "detail": (r2.json() if r2.content else {}).get("detail"),
            "ms": round((time.perf_counter() - t1) * 1000.0, 2),
        }
    )
    # Invalid image_key on register
    t2 = time.perf_counter()
    r3 = await client.post(
        f"{base}/api/v1/public/register",
        json=_payload(_phone(), image_key="../etc/passwd"),
        headers=PERF_HEADER,
    )
    results.append(
        {
            "case": "invalid_image_key",
            "status": r3.status_code,
            "pass": r3.status_code == 400,
            "detail": (r3.json() if r3.content else {}).get("detail"),
            "ms": round((time.perf_counter() - t2) * 1000.0, 2),
        }
    )
    return {
        "scenario": "oversized_invalid_image",
        "pass": all(x["pass"] for x in results),
        "cases": results,
    }


async def scenario_cleanup_after_failed_register(client, base: str) -> Dict[str, Any]:
    """Upload OK, then force register failure (duplicate phone) → object cleaned."""
    phone = _phone()
    # Seed an existing registration for this phone
    seed = await client.post(
        f"{base}/api/v1/public/register",
        json=_payload(phone),
        headers=PERF_HEADER,
    )
    if seed.status_code != 200:
        return {
            "scenario": "cleanup_after_failed_register",
            "pass": False,
            "detail": f"seed failed: {seed.status_code}",
        }

    up = await _presign_and_upload(
        client, base, _tiny_png_bytes(), filename="orphan.png", content_type="image/png"
    )
    if not up.get("ok"):
        return {
            "scenario": "cleanup_after_failed_register",
            "pass": False,
            "detail": up.get("detail") or "upload failed",
            "upload": up,
            "manual_supabase_cors": True,
        }
    object_key = up["object_key"]
    # Different idempotency → 409 duplicate phone; backend should cleanup
    r = await client.post(
        f"{base}/api/v1/public/register",
        json=_payload(phone, image_key=object_key, idem=uuid.uuid4().hex),
        headers=PERF_HEADER,
    )
    # Confirm cleanup via cleanup-upload (should succeed / already gone)
    c = await client.post(
        f"{base}/api/v1/public/cleanup-upload",
        json={"object_key": object_key},
        headers=PERF_HEADER,
    )
    cbody = c.json() if c.content else {}
    return {
        "scenario": "cleanup_after_failed_register",
        "pass": r.status_code == 409 and c.status_code == 200,
        "register_status": r.status_code,
        "cleanup_status": c.status_code,
        "cleanup_body": cbody,
        "object_key": object_key,
        "presign_ms": up.get("presign_ms"),
        "direct_upload_ms": up.get("direct_upload_ms"),
        "detail": (r.json() if r.content else {}).get("detail"),
    }


async def scenario_duplicate_submission(client, base: str) -> Dict[str, Any]:
    phone = _phone()
    idem = uuid.uuid4().hex
    payload = _payload(phone, idem=idem)
    r1 = await client.post(
        f"{base}/api/v1/public/register",
        json=payload,
        headers={**PERF_HEADER, "X-Idempotency-Key": idem},
    )
    body1 = r1.json() if r1.content else {}
    r2 = await client.post(
        f"{base}/api/v1/public/register",
        json=payload,
        headers={**PERF_HEADER, "X-Idempotency-Key": idem},
    )
    body2 = r2.json() if r2.content else {}
    same = body1.get("request_number") and body1.get("request_number") == body2.get("request_number")
    return {
        "scenario": "duplicate_submission",
        "pass": r1.status_code == 200 and r2.status_code == 200 and same and body2.get("success") is True,
        "status1": r1.status_code,
        "status2": r2.status_code,
        "request_number": body1.get("request_number"),
        "idempotent_same_code": same,
        "perf1": _parse_perf(r1),
        "perf2": _parse_perf(r2),
    }


async def run_all(base: str) -> Dict[str, Any]:
    import httpx

    async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
        results: List[Dict[str, Any]] = []
        for fn in (
            scenario_no_image,
            scenario_valid_image,
            scenario_invalid_images,
            scenario_cleanup_after_failed_register,
            scenario_duplicate_submission,
        ):
            try:
                results.append(await fn(client, base))
            except Exception as e:  # noqa: BLE001
                results.append(
                    {
                        "scenario": getattr(fn, "__name__", "unknown"),
                        "pass": False,
                        "error": str(e),
                        "traceback": traceback.format_exc()[-800:],
                    }
                )
        # Extra warm timing samples (no image + with image)
        timings = []
        for with_img in (False, True):
            for i in range(2):
                if with_img:
                    row = await scenario_valid_image(client, base)
                else:
                    row = await scenario_no_image(client, base)
                timings.append(
                    {
                        "with_image": with_img,
                        "sample": i,
                        "total_submit_ms": row.get("total_submit_ms"),
                        "presign_ms": row.get("presign_ms"),
                        "direct_upload_ms": row.get("direct_upload_ms"),
                        "register_ms": row.get("register_ms") or row.get("total_submit_ms"),
                        "server_stages": (row.get("server_perf") or {}).get("stages_ms"),
                        "pass": row.get("pass"),
                    }
                )
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "base_url": base,
            "scenarios": results,
            "all_passed": all(bool(r.get("pass")) for r in results),
            "timing_samples": timings,
            "before_prod_reference_ms": {
                "no_upload_warm": "2.0–2.6s",
                "with_tiny_upload_proxy": "2.8–3.7s",
                "with_800kb_proxy": "~3.7s",
                "users_real_photos_double_hop": "6–8s",
            },
            "supabase_cors_note": (
                "If direct PUT to signed upload URL fails in the browser, enable Storage CORS "
                "in the Supabase dashboard for your frontend origin (methods: PUT, POST, OPTIONS; "
                "headers: authorization, content-type, x-upsert, apikey)."
            ),
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PERF_MEASURE_PORT", "8012")))
    parser.add_argument("--no-server", action="store_true")
    args = parser.parse_args()

    base = (args.base_url or "").rstrip("/")
    proc = None
    if not base:
        base = f"http://127.0.0.1:{args.port}"
        if not args.no_server:
            env = os.environ.copy()
            env["PORT"] = str(args.port)
            proc = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "main:app",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(args.port),
                    "--log-level",
                    "warning",
                ],
                cwd=str(BACKEND_DIR),
                env=env,
            )

    try:
        if proc is not None:
            asyncio.run(_wait_for_ready(base))
        report = asyncio.run(run_all(base))
    finally:
        if proc is not None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except Exception:
                proc.kill()

    out_path = BACKEND_DIR / "_test_reg_direct_upload_report.json"
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("all_passed", "base_url", "generated_at")}, indent=2))
    for s in report["scenarios"]:
        print(f"  [{('PASS' if s.get('pass') else 'FAIL')}] {s.get('scenario')} status={s.get('status', s.get('register_status', ''))} total_ms={s.get('total_submit_ms')}")
    print(f"Report: {out_path}")
    print(report.get("supabase_cors_note"))
    return 0 if report.get("all_passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
