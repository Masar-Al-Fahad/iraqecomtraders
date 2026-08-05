"""
MEASUREMENT-ONLY harness — temporary, opt-in, no business-logic changes.

Usage (from backend/):
  .venv\\Scripts\\python.exe _perf_measure_run.py

Attaches request-timing middleware + SQLAlchemy query timing listeners,
starts uvicorn against local .env (Supabase DATABASE_URL), hits representative
endpoints, prints Top-10 slowest requests, then exits.
"""
from __future__ import annotations

import asyncio
import json
import os
import statistics
import sys
import threading
import time
import traceback
from contextvars import ContextVar
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# Ensure backend root on path
BACKEND_DIR = Path(__file__).resolve().parent
os.chdir(BACKEND_DIR)
sys.path.insert(0, str(BACKEND_DIR))

from dotenv import load_dotenv

load_dotenv(BACKEND_DIR / ".env", override=True)

# ---------------------------------------------------------------------------
# Per-request query timing via contextvars + SQLAlchemy events
# ---------------------------------------------------------------------------
_req_db_ms: ContextVar[Optional[List[float]]] = ContextVar("_req_db_ms", default=None)
_req_db_count: ContextVar[Optional[List[int]]] = ContextVar("_req_db_count", default=None)

RESULTS: List[Dict[str, Any]] = []
RESULTS_LOCK = threading.Lock()


@dataclass
class QueryBucket:
    times_ms: List[float] = field(default_factory=list)

    @property
    def total_ms(self) -> float:
        return sum(self.times_ms)

    @property
    def count(self) -> int:
        return len(self.times_ms)


def _install_sqlalchemy_listeners(engine) -> None:
    from sqlalchemy import event

    sync_engine = getattr(engine, "sync_engine", engine)

    @event.listens_for(sync_engine, "before_cursor_execute")
    def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):  # noqa: ARG001
        conn.info["query_start_time"] = time.perf_counter()

    @event.listens_for(sync_engine, "after_cursor_execute")
    def after_cursor_execute(conn, cursor, statement, parameters, context, executemany):  # noqa: ARG001
        start = conn.info.pop("query_start_time", None)
        if start is None:
            return
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        bucket = _req_db_ms.get()
        if bucket is not None:
            bucket.append(elapsed_ms)


def _install_timing_middleware(app) -> None:
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.requests import Request
    from starlette.responses import Response

    class PerfTimingMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next) -> Response:
            db_times: List[float] = []
            token = _req_db_ms.set(db_times)
            t0 = time.perf_counter()
            status_code = 500
            try:
                response = await call_next(request)
                status_code = response.status_code
                return response
            finally:
                total_ms = (time.perf_counter() - t0) * 1000.0
                db_total = sum(db_times)
                db_count = len(db_times)
                _req_db_ms.reset(token)
                # Skip noisy static-ish paths if any
                path = request.url.path
                rec = {
                    "method": request.method,
                    "path": path,
                    "query": str(request.url.query) if request.url.query else "",
                    "status": status_code,
                    "total_ms": round(total_ms, 2),
                    "db_ms": round(db_total, 2),
                    "db_queries": db_count,
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "source": "middleware",
                }
                with RESULTS_LOCK:
                    RESULTS.append(rec)
                # Also emit one-line log for session review
                print(
                    f"[PERF] {request.method} {path} status={status_code} "
                    f"total_ms={total_ms:.1f} db_ms={db_total:.1f} queries={db_count}",
                    flush=True,
                )

    # Add outermost so it wraps the whole request
    app.add_middleware(PerfTimingMiddleware)


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


async def _measure_client(base: str) -> List[Dict[str, Any]]:
    """Hit representative endpoints; client-side wall clock as secondary measure."""
    import httpx

    client_results: List[Dict[str, Any]] = []

    async def hit(
        method: str,
        path: str,
        *,
        headers: Optional[Dict[str, str]] = None,
        json_body: Any = None,
        label: Optional[str] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> httpx.Response:
        url = f"{base}{path}"
        t0 = time.perf_counter()
        async with httpx.AsyncClient(timeout=120.0, follow_redirects=False) as client:
            r = await client.request(method, url, headers=headers, json=json_body, params=params)
        elapsed = (time.perf_counter() - t0) * 1000.0
        client_results.append(
            {
                "method": method,
                "path": path,
                "label": label or path,
                "status": r.status_code,
                "client_total_ms": round(elapsed, 2),
                "source": "httpx_client",
            }
        )
        print(
            f"[CLIENT] {method} {path} status={r.status_code} client_ms={elapsed:.1f}",
            flush=True,
        )
        return r

    # --- Public / unauthenticated ---
    await hit("GET", "/")
    await hit("GET", "/health")
    await hit("GET", "/database/health")
    await hit("GET", "/api/v1/public/app-settings/brand")
    await hit("GET", "/api/v1/public/app-settings/registration-form")

    # --- Login ---
    username = os.environ.get("SUPER_ADMIN_USERNAME", "admin")
    password = os.environ.get("SUPER_ADMIN_PASSWORD", "")
    if not password:
        print("[WARN] SUPER_ADMIN_PASSWORD empty — skipping auth endpoints", flush=True)
        return client_results

    login_r = await hit(
        "POST",
        "/api/v1/auth/login",
        json_body={"username": username, "password": password},
        label="auth.login",
    )
    token = None
    if login_r.status_code == 200:
        token = login_r.json().get("token")
    else:
        print(f"[WARN] Login failed: {login_r.status_code} {login_r.text[:200]}", flush=True)
        return client_results

    auth = {"Authorization": f"Bearer {token}"}

    # --- Admin dashboard waterfall (same order as AdminDashboard.tsx) ---
    await hit("GET", "/api/v1/auth/me", headers=auth, label="auth.me")
    await hit("GET", "/api/v1/admin/registrations/check-admin", headers=auth, label="check-admin")
    # Parallel-ish group after auth (we measure sequentially for clear attribution)
    await hit("GET", "/api/v1/admin/registrations/stats", headers=auth, label="stats")
    await hit(
        "GET",
        "/api/v1/admin/registrations",
        headers=auth,
        params={"skip": 0, "limit": 50, "sort": "-created_at"},
        label="registrations.list",
    )
    await hit(
        "GET",
        "/api/v1/admin/registrations/next-membership-number",
        headers=auth,
        label="next-membership-number",
    )
    await hit(
        "GET",
        "/api/v1/admin/registrations/next-application-number",
        headers=auth,
        label="next-application-number",
    )

    # --- Other admin surfaces ---
    await hit("GET", "/api/v1/admin/users", headers=auth, label="admin.users")
    await hit("GET", "/api/v1/admin/app-settings/brand", headers=auth, label="admin.brand")
    await hit(
        "GET",
        "/api/v1/admin/app-settings/registration-form",
        headers=auth,
        label="admin.registration-form",
    )
    await hit(
        "GET",
        "/api/v1/admin/audit-log",
        headers=auth,
        params={"skip": 0, "limit": 50},
        label="audit-log",
    )
    await hit("GET", "/api/v1/admin/settings", headers=auth, label="admin.settings")

    # Heavier reads (may be slow / large)
    await hit(
        "GET",
        "/api/v1/admin/registrations/export-all",
        headers=auth,
        params={"sort": "-created_at"},
        label="export-all",
    )
    await hit(
        "GET",
        "/api/v1/admin/registrations/print-data",
        headers=auth,
        params={"skip": 0, "limit": 50, "sort": "-created_at"},
        label="print-data",
    )
    await hit(
        "GET",
        "/api/v1/admin/registrations/export-xlsx",
        headers=auth,
        params={"sort": "-created_at"},
        label="export-xlsx",
    )

    # Entity CRUD list (template route)
    await hit(
        "GET",
        "/api/v1/entities/registrations",
        headers=auth,
        params={"skip": 0, "limit": 20},
        label="entities.registrations",
    )

    # Repeat warm-path once for comparison (list + stats)
    await hit("GET", "/api/v1/admin/registrations/stats", headers=auth, label="stats.warm")
    await hit(
        "GET",
        "/api/v1/admin/registrations",
        headers=auth,
        params={"skip": 0, "limit": 50, "sort": "-created_at"},
        label="registrations.list.warm",
    )

    return client_results


def _merge_top10(middleware_rows: List[Dict[str, Any]], client_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Prefer middleware rows (include DB timing). Dedupe by method+path keeping slowest."""
    # Filter out the measurement probe noise: only API-ish routes we care about
    # Keep all middleware measurements that look like real API hits during our run.
    by_key: Dict[str, Dict[str, Any]] = {}
    for row in middleware_rows:
        # Normalize path without query for grouping; keep slowest occurrence
        key = f"{row['method']} {row['path']}"
        prev = by_key.get(key)
        if prev is None or row["total_ms"] > prev["total_ms"]:
            by_key[key] = dict(row)

    # Attach best client_ms match when available
    client_by_path = {}
    for c in client_rows:
        # strip query from client path if present
        p = c["path"].split("?")[0]
        key = f"{c['method']} {p}"
        prev = client_by_path.get(key)
        if prev is None or c["client_total_ms"] > prev["client_total_ms"]:
            client_by_path[key] = c

    merged = []
    for key, row in by_key.items():
        c = client_by_path.get(key)
        if c:
            row["client_total_ms"] = c["client_total_ms"]
            row["label"] = c.get("label")
        merged.append(row)

    merged.sort(key=lambda r: r["total_ms"], reverse=True)
    return merged[:10]


def _print_report(top10: List[Dict[str, Any]], client_rows: List[Dict[str, Any]], all_mw: List[Dict[str, Any]]) -> str:
    lines: List[str] = []
    lines.append("=" * 72)
    lines.append("PERFORMANCE REPORT / تقرير الأداء")
    lines.append(f"Generated: {datetime.now(timezone.utc).isoformat()}")
    lines.append("Target: LOCAL uvicorn + Supabase DATABASE_URL (not Railway production)")
    lines.append("=" * 72)
    lines.append("")
    lines.append("TOP 10 SLOWEST REQUESTS (server middleware wall-clock)")
    lines.append("-" * 72)
    for i, r in enumerate(top10, 1):
        db_note = f"DB {r.get('db_ms', 0):.1f} ms / {r.get('db_queries', 0)} queries"
        client_note = f" | client {r['client_total_ms']:.1f} ms" if "client_total_ms" in r else ""
        label = f" ({r['label']})" if r.get("label") else ""
        lines.append(
            f"{i:2d}. {r['method']:6s} {r['path']}{label}\n"
            f"    total={r['total_ms']:.1f} ms | {db_note}{client_note} | HTTP {r.get('status')}"
        )
    lines.append("")
    lines.append("METHOD / المنهجية")
    lines.append("-" * 72)
    lines.append(
        "- Temporary opt-in middleware (PerfTimingMiddleware) wrapping each request; "
        "no route/handler/business logic changed."
    )
    lines.append(
        "- SQLAlchemy sync-engine before/after_cursor_execute listeners accumulate "
        "query durations into a request ContextVar (db_ms / db_queries)."
    )
    lines.append(
        "- External httpx client hits public + authenticated admin endpoints; "
        "login uses SUPER_ADMIN_* from backend/.env (password not printed)."
    )
    lines.append(
        "- Top-10 ranked by slowest server-side total_ms per unique METHOD+path "
        "(warm repeats: keep max)."
    )
    lines.append(f"- Middleware samples collected: {len(all_mw)}; client probes: {len(client_rows)}")
    lines.append("")
    lines.append("ADMIN DASHBOARD API WATERFALL (frontend context only)")
    lines.append("-" * 72)
    lines.append("1. GET /api/v1/auth/me")
    lines.append("2. GET /api/v1/admin/registrations/check-admin")
    lines.append("3. (in parallel after authorized) GET .../registrations?...")
    lines.append("4. (parallel) GET .../registrations/stats")
    lines.append("5. (if edit perm) GET .../next-membership-number")
    lines.append("6. (if edit perm) GET .../next-application-number")
    lines.append("")
    return "\n".join(lines)


async def _async_main() -> int:
    import uvicorn
    from main import app
    from core.database import db_manager

    # Initialize DB early so we can attach listeners before requests
    await db_manager.init_db()
    _install_sqlalchemy_listeners(db_manager.engine)
    _install_timing_middleware(app)

    port = int(os.environ.get("PORT", "8000"))
    # Use a dedicated measurement port to avoid clashing with a running server
    measure_port = int(os.environ.get("PERF_MEASURE_PORT", "8010"))
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

    try:
        # Wait until lifespan has finished DB init (server.started)
        for _ in range(180):
            if getattr(server, "started", False):
                break
            await asyncio.sleep(0.25)
        await _wait_for_ready(base, timeout=90.0)

        # Re-attach listeners in case lifespan recreated engine... engine should be same
        if db_manager.engine:
            _install_sqlalchemy_listeners(db_manager.engine)

        client_rows = await _measure_client(base)
        # Allow in-flight middleware records to flush
        await asyncio.sleep(0.5)

        with RESULTS_LOCK:
            mw_rows = list(RESULTS)

        top10 = _merge_top10(mw_rows, client_rows)
        report = _print_report(top10, client_rows, mw_rows)

        out_path = BACKEND_DIR / "_perf_measure_report.json"
        payload = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "target": "local_uvicorn_supabase",
            "railway_production_hit": False,
            "base_url": base,
            "top10": top10,
            "all_middleware": mw_rows,
            "client_probes": client_rows,
            "report_text": report,
        }
        out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        # Windows consoles may be cp1252 — write UTF-8 report file and print ASCII-safe
        report_txt = BACKEND_DIR / "_perf_measure_report.txt"
        report_txt.write_text(report, encoding="utf-8")
        try:
            print(report)
        except UnicodeEncodeError:
            print(report.encode("ascii", errors="replace").decode("ascii"))
        print(f"\nJSON written to: {out_path}")
        print(f"TXT written to: {report_txt}")
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
    # Avoid reload; run measurement once
    os.environ.setdefault("ENVIRONMENT", "dev")
    raise SystemExit(asyncio.run(_async_main()))


if __name__ == "__main__":
    main()
