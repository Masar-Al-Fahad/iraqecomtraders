"""Opt-in stage timing for public registration submit (header X-Reg-Perf: 1).

Production-safe: timing + request id only — never passwords, tokens, PII, or file bytes.
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Dict, Iterator, Optional

logger = logging.getLogger(__name__)

_stages: ContextVar[Optional[Dict[str, float]]] = ContextVar("reg_perf_stages", default=None)
_enabled: ContextVar[bool] = ContextVar("reg_perf_enabled", default=False)
_request_id: ContextVar[Optional[str]] = ContextVar("reg_perf_request_id", default=None)
_t_request_start: ContextVar[Optional[float]] = ContextVar("reg_perf_t0", default=None)

HEADER_REQUEST = "x-reg-perf"
HEADER_RESPONSE = "X-Reg-Perf-Stages"
HEADER_REQUEST_ID = "X-Request-Id"


def enable_from_request(request) -> str:
    """Always assign a request id; enable detailed stage timings when X-Reg-Perf: 1.

    Returns the request id (also stored in ContextVar).
    """
    incoming = (request.headers.get("x-request-id") or "").strip()
    rid = incoming if incoming and len(incoming) <= 64 else uuid.uuid4().hex
    _request_id.set(rid)
    _t_request_start.set(time.perf_counter())

    raw = (request.headers.get(HEADER_REQUEST) or "").strip().lower()
    enabled = raw in ("1", "true", "yes")
    _enabled.set(enabled)
    # Always keep a stages bucket so key REG_TIMING logs can record stages;
    # detailed response header only when opt-in.
    _stages.set({})
    if enabled:
        record("request_received", 0.0)
    return rid


def request_id() -> Optional[str]:
    return _request_id.get()


def is_enabled() -> bool:
    return bool(_enabled.get())


@contextmanager
def stage(name: str) -> Iterator[None]:
    # Record whenever a stages bucket is present (request id always assigned).
    # Opt-in header only controls whether stages are returned to the client.
    bucket = _stages.get()
    if bucket is None:
        yield
        return
    t0 = time.perf_counter()
    try:
        yield
    finally:
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        bucket[name] = round(bucket.get(name, 0.0) + elapsed_ms, 2)


def record(name: str, elapsed_ms: float) -> None:
    bucket = _stages.get()
    if bucket is not None:
        bucket[name] = round(bucket.get(name, 0.0) + float(elapsed_ms), 2)


def mark_since_start(name: str) -> None:
    """Record wall time from request enable → now (overlap-aware absolute mark)."""
    t0 = _t_request_start.get()
    if t0 is None:
        return
    record(name, (time.perf_counter() - t0) * 1000.0)


def snapshot() -> Dict[str, Any]:
    bucket = _stages.get() or {}
    total = round(sum(bucket.values()), 2) if bucket else 0.0
    return {
        "request_id": _request_id.get(),
        "stages_ms": dict(bucket),
        "sum_stages_ms": total,
    }


def response_header_value() -> Optional[str]:
    if not _enabled.get():
        return None
    return json.dumps(snapshot(), separators=(",", ":"), ensure_ascii=False)


def apply_response_headers(headers: Dict[str, str]) -> Dict[str, str]:
    """Attach X-Request-Id always; X-Reg-Perf-Stages when opt-in enabled."""
    rid = _request_id.get()
    if rid:
        headers[HEADER_REQUEST_ID] = rid
    perf_hdr = response_header_value()
    if perf_hdr:
        headers[HEADER_RESPONSE] = perf_hdr
        # Timing-only log (no PII)
        logger.info("REG_PERF rid=%s %s", rid, perf_hdr)
    return headers
