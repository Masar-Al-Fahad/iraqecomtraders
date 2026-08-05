"""
Profile public registration submit stages (measure-only harness).

Usage (from backend/):
  .venv\\Scripts\\python.exe _reg_submit_profile.py
  .venv\\Scripts\\python.exe _reg_submit_profile.py --label before
  .venv\\Scripts\\python.exe _reg_submit_profile.py --label after

Starts a local uvicorn on PERF_MEASURE_PORT (default 8011), simulates the
frontend submit path with and without file upload, prints stage timings.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
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


def _parse_perf_header(resp) -> Dict[str, Any]:
    raw = resp.headers.get("x-reg-perf-stages") or resp.headers.get("X-Reg-Perf-Stages")
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except Exception:
        return {"raw": raw}


def _tiny_png_bytes() -> bytes:
    # 1x1 PNG
    import base64

    return base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    )


async def _run_flow(
    client,
    base: str,
    *,
    with_upload: bool,
) -> Dict[str, Any]:
    stages_client: Dict[str, float] = {}
    server_upload: Dict[str, Any] = {}
    server_register: Dict[str, Any] = {}
    t_total = time.perf_counter()
    # 07 + 9 digits — unique per run (avoid 409 collisions across warm/profile)
    phone = "07" + f"{random.SystemRandom().randint(0, 10**9 - 1):09d}"
    run_id = uuid.uuid4().hex[:12]

    t0 = time.perf_counter()
    # Mirrors frontend validation + payload prep (local, no network)
    payload = {
        "business_name": f"Perf Biz {run_id}",
        "merchant_name": "Perf Merchant",
        "phone": phone,
        "governorate": "بغداد",
        "area": "الكرادة",
        "business_type": "تجارة",
        "notes": "reg-submit-profile",
        "image_key": "manual_entry",
        "extra_fields": {},
    }
    stages_client["frontend_validation_payload_prep"] = round((time.perf_counter() - t0) * 1000.0, 2)

    final_key = "manual_entry"
    if with_upload:
        object_key = f"registrations/perf_{int(time.time() * 1000)}_{run_id}.png"
        # Match optimized frontend: call upload-file directly (no upload-url RTT)
        upload_url = f"{base}/api/v1/public/upload-file?object_key={object_key}"
        t0 = time.perf_counter()
        put = await client.put(
            upload_url,
            content=_tiny_png_bytes(),
            headers={**PERF_HEADER, "Content-Type": "image/png"},
        )
        stages_client["file_upload_put_network"] = round((time.perf_counter() - t0) * 1000.0, 2)
        server_upload = _parse_perf_header(put)
        if put.status_code >= 400:
            raise RuntimeError(f"upload failed {put.status_code}: {put.text[:300]}")
        put_data = put.json()
        final_key = put_data.get("object_key") or object_key

    payload["image_key"] = final_key

    t0 = time.perf_counter()
    idem = f"perf-{uuid.uuid4().hex}"
    payload["idempotency_key"] = idem
    reg = await client.post(
        f"{base}/api/v1/public/register",
        json=payload,
        headers={**PERF_HEADER, "X-Idempotency-Key": idem},
    )
    stages_client["post_register_network"] = round((time.perf_counter() - t0) * 1000.0, 2)
    server_register = _parse_perf_header(reg)
    body = {}
    try:
        body = reg.json()
    except Exception:
        body = {"raw": reg.text[:500]}
    if reg.status_code >= 400:
        raise RuntimeError(f"register failed {reg.status_code}: {body}")

    total_ms = round((time.perf_counter() - t_total) * 1000.0, 2)
    return {
        "with_upload": with_upload,
        "status": reg.status_code,
        "request_number": body.get("request_number"),
        "client_stages_ms": stages_client,
        "server_upload": server_upload,
        "server_register": server_register,
        "total_submit_ms": total_ms,
    }


def _print_result(label: str, row: Dict[str, Any]) -> None:
    kind = "WITH upload" if row["with_upload"] else "WITHOUT upload"
    print(f"\n=== {label} / {kind} ===")
    print(f"total_submit_ms: {row['total_submit_ms']}")
    print(f"request_number: {row.get('request_number')}")
    print("client stages:")
    for k, v in (row.get("client_stages_ms") or {}).items():
        print(f"  {k}: {v} ms")
    sr = row.get("server_register") or {}
    print("server register stages:")
    for k, v in (sr.get("stages_ms") or {}).items():
        print(f"  {k}: {v} ms")
    if row.get("with_upload"):
        su = row.get("server_upload") or {}
        print("server upload stages:")
        for k, v in (su.get("stages_ms") or {}).items():
            print(f"  {k}: {v} ms")


async def _async_main(label: str) -> int:
    import httpx
    import uvicorn
    from main import app
    from core.database import db_manager

    measure_port = int(os.environ.get("PERF_MEASURE_PORT", "8011"))
    base = f"http://127.0.0.1:{measure_port}"

    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=measure_port,
        log_level="warning",
        access_log=False,
    )
    server = uvicorn.Server(config)
    serve_task = asyncio.create_task(server.serve())

    results: List[Dict[str, Any]] = []
    try:
        for _ in range(180):
            if getattr(server, "started", False):
                break
            await asyncio.sleep(0.25)
        await _wait_for_ready(base, timeout=90.0)

        # Warm schema / connections
        async with httpx.AsyncClient(timeout=120.0) as client:
            await client.get(f"{base}/health")
            warm = await _run_flow(client, base, with_upload=False)
            print(f"[warm] total={warm['total_submit_ms']} ms req={warm.get('request_number')}")

            no_up = await _run_flow(client, base, with_upload=False)
            results.append(no_up)
            _print_result(label, no_up)

            with_up = await _run_flow(client, base, with_upload=True)
            results.append(with_up)
            _print_result(label, with_up)

        out = {
            "label": label,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "base_url": base,
            "results": results,
        }
        out_path = BACKEND_DIR / f"_reg_submit_profile_{label}.json"
        out_path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\nWrote {out_path}")
        return 0
    except Exception:
        traceback.print_exc()
        return 1
    finally:
        server.should_exit = True
        try:
            await asyncio.wait_for(serve_task, timeout=15.0)
        except Exception:
            serve_task.cancel()
        try:
            await db_manager.close_db()
        except Exception:
            pass


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", default="before", help="before|after|custom")
    args = parser.parse_args()
    os.environ.setdefault("ENVIRONMENT", "dev")
    raise SystemExit(asyncio.run(_async_main(args.label)))


if __name__ == "__main__":
    main()
