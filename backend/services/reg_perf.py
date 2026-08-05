"""Opt-in stage timing for public registration submit (header X-Reg-Perf: 1)."""
from __future__ import annotations

import json
import time
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Dict, Iterator, Optional

_stages: ContextVar[Optional[Dict[str, float]]] = ContextVar("reg_perf_stages", default=None)
_enabled: ContextVar[bool] = ContextVar("reg_perf_enabled", default=False)

HEADER_REQUEST = "x-reg-perf"
HEADER_RESPONSE = "X-Reg-Perf-Stages"


def enable_from_request(request) -> None:
    raw = (request.headers.get(HEADER_REQUEST) or "").strip().lower()
    _enabled.set(raw in ("1", "true", "yes"))
    if _enabled.get():
        _stages.set({})
    else:
        _stages.set(None)


def is_enabled() -> bool:
    return bool(_enabled.get())


@contextmanager
def stage(name: str) -> Iterator[None]:
    if not _enabled.get():
        yield
        return
    t0 = time.perf_counter()
    try:
        yield
    finally:
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        bucket = _stages.get()
        if bucket is not None:
            bucket[name] = round(bucket.get(name, 0.0) + elapsed_ms, 2)


def record(name: str, elapsed_ms: float) -> None:
    if not _enabled.get():
        return
    bucket = _stages.get()
    if bucket is not None:
        bucket[name] = round(bucket.get(name, 0.0) + float(elapsed_ms), 2)


def snapshot() -> Dict[str, Any]:
    bucket = _stages.get() or {}
    total = round(sum(bucket.values()), 2) if bucket else 0.0
    return {"stages_ms": dict(bucket), "sum_stages_ms": total}


def response_header_value() -> Optional[str]:
    if not _enabled.get():
        return None
    return json.dumps(snapshot(), separators=(",", ":"), ensure_ascii=False)
