"""Quick idempotency + multi-sample timing check for public register."""
from __future__ import annotations

import asyncio
import json
import os
import random
import sys
import time
import uuid
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
os.chdir(BACKEND_DIR)
sys.path.insert(0, str(BACKEND_DIR))

from dotenv import load_dotenv

load_dotenv(BACKEND_DIR / ".env", override=True)


async def main() -> int:
    import httpx
    import uvicorn
    from core.database import db_manager
    from main import app

    port = int(os.environ.get("PERF_MEASURE_PORT", "8013"))
    base = f"http://127.0.0.1:{port}"
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error", access_log=False)
    )
    task = asyncio.create_task(server.serve())
    try:
        for _ in range(180):
            if getattr(server, "started", False):
                break
            await asyncio.sleep(0.25)
        async with httpx.AsyncClient(timeout=120.0) as c:
            for _ in range(60):
                try:
                    if (await c.get(f"{base}/health")).status_code == 200:
                        break
                except Exception:
                    pass
                await asyncio.sleep(0.5)

            samples = []
            for _ in range(3):
                phone = "07" + f"{random.SystemRandom().randint(0, 10**9 - 1):09d}"
                idem = uuid.uuid4().hex
                payload = {
                    "business_name": "Bench",
                    "merchant_name": "M",
                    "phone": phone,
                    "governorate": "g",
                    "area": "a",
                    "business_type": "t",
                    "image_key": "manual_entry",
                    "notes": "",
                    "extra_fields": {},
                    "idempotency_key": idem,
                }
                t0 = time.perf_counter()
                r = await c.post(
                    f"{base}/api/v1/public/register",
                    json=payload,
                    headers={"X-Reg-Perf": "1", "X-Idempotency-Key": idem},
                )
                total = (time.perf_counter() - t0) * 1000
                body = r.json()
                stages = r.headers.get("x-reg-perf-stages")
                t1 = time.perf_counter()
                r2 = await c.post(
                    f"{base}/api/v1/public/register",
                    json=payload,
                    headers={"X-Idempotency-Key": idem},
                )
                replay_ms = (time.perf_counter() - t1) * 1000
                body2 = r2.json()
                samples.append(
                    {
                        "status": r.status_code,
                        "total_ms": round(total, 1),
                        "request_number": body.get("request_number"),
                        "stages": json.loads(stages) if stages else {},
                        "idempotent_status": r2.status_code,
                        "idempotent_request_number": body2.get("request_number"),
                        "idempotent_ms": round(replay_ms, 1),
                        "idempotent_same_code": body.get("request_number")
                        == body2.get("request_number"),
                    }
                )

            out = BACKEND_DIR / "_reg_submit_idempotency_test.json"
            out.write_text(json.dumps(samples, indent=2, ensure_ascii=False), encoding="utf-8")
            print(f"Wrote {out}")
            for s in samples:
                print(
                    f"status={s['status']} total_ms={s['total_ms']} rn={s['request_number']} "
                    f"idem_status={s['idempotent_status']} same={s['idempotent_same_code']}"
                )
            ok = all(
                s["status"] == 200
                and s["idempotent_status"] == 200
                and s["idempotent_same_code"]
                for s in samples
            )
            return 0 if ok else 1
    finally:
        server.should_exit = True
        try:
            await asyncio.wait_for(task, timeout=10)
        except Exception:
            task.cancel()
        try:
            await db_manager.close_db()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
