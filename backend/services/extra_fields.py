"""Helpers for dynamic registration form field values (JSON in extra_fields column)."""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional, Sequence

logger = logging.getLogger(__name__)

CORE_FIELD_IDS = {
    "business_name",
    "merchant_name",
    "phone",
    "governorate",
    "area",
    "business_type",
    "notes",
    "image_key",
    "terms",
    "image",
}


def dumps_extra_fields(data: Any) -> str:
    if not data:
        return "{}"
    if isinstance(data, str):
        try:
            parsed = json.loads(data)
            if isinstance(parsed, dict):
                return json.dumps(parsed, ensure_ascii=False)
        except Exception:
            return "{}"
        return "{}"
    if isinstance(data, dict):
        clean: Dict[str, Any] = {}
        for key, val in data.items():
            if val is None:
                continue
            if isinstance(val, dict):
                label = str(val.get("label") or key)
                value = val.get("value")
                if value is None or value == "":
                    continue
                clean[str(key)] = {"label": label, "value": value}
            else:
                clean[str(key)] = {"label": str(key), "value": val}
        return json.dumps(clean, ensure_ascii=False)
    return "{}"


def loads_extra_fields(raw: Any) -> Dict[str, Dict[str, Any]]:
    if not raw:
        return {}
    if isinstance(raw, dict):
        return {str(k): (v if isinstance(v, dict) else {"label": str(k), "value": v}) for k, v in raw.items()}
    if isinstance(raw, str):
        try:
            data = json.loads(raw)
        except Exception:
            return {}
        if isinstance(data, dict):
            out: Dict[str, Dict[str, Any]] = {}
            for k, v in data.items():
                if isinstance(v, dict):
                    out[str(k)] = {
                        "label": str(v.get("label") or k),
                        "value": v.get("value"),
                    }
                else:
                    out[str(k)] = {"label": str(k), "value": v}
            return out
    return {}


def dynamic_field_defs(form_settings: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Return visible custom fields from registration form settings (dynamic, not hardcoded)."""
    form_settings = form_settings or {}
    fields = form_settings.get("fields") or []
    out: List[Dict[str, Any]] = []
    for f in fields:
        if not isinstance(f, dict):
            continue
        fid = str(f.get("id") or "")
        if not fid or fid in CORE_FIELD_IDS:
            continue
        maps_to = f.get("maps_to")
        if maps_to in CORE_FIELD_IDS:
            continue
        if f.get("type") in ("image_upload", "file_upload", "checkbox") and fid == "terms":
            continue
        if f.get("type") in ("image_upload", "file_upload"):
            continue
        if f.get("type") == "checkbox" and (maps_to is None or fid.startswith("terms")):
            # skip terms-like checkboxes
            label = str(f.get("label") or "")
            if "أوافق" in label or fid == "terms":
                continue
        if f.get("visible") is False:
            continue
        out.append(f)
    out.sort(key=lambda x: int(x.get("order") or 0))
    return out


def _parse_notes_map(notes: str) -> Dict[str, str]:
    """Parse 'Label: value' lines from notes into a label→value map."""
    result: Dict[str, str] = {}
    if not notes:
        return result
    for line in str(notes).splitlines():
        line = line.strip()
        if not line or ":" not in line:
            continue
        label, value = line.split(":", 1)
        label = label.strip()
        value = value.strip()
        if label and value:
            result[label] = value
    return result


def _norm_label(s: str) -> str:
    return "".join(str(s or "").split()).casefold()


def _labels_match(a: str, b: str) -> bool:
    na, nb = _norm_label(a), _norm_label(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    # tolerate minor typos / renames (substring overlap)
    if len(na) >= 4 and len(nb) >= 4 and (na in nb or nb in na):
        return True
    return False


def resolve_member_extra_fields(
    item: Any,
    form_settings: Optional[Dict[str, Any]] = None,
) -> Dict[str, Dict[str, Any]]:
    """
    Merge structured extra_fields with values recovered from notes lines
    for known dynamic form fields (backward compatible).
    """
    data = loads_extra_fields(getattr(item, "extra_fields", None))
    defs = dynamic_field_defs(form_settings)
    notes_map = _parse_notes_map(getattr(item, "notes", None) or "")
    used_notes: set = set()

    if not defs:
        for label, value in notes_map.items():
            already = any(_labels_match(str(v.get("label") or ""), label) for v in data.values())
            if not already:
                data[f"note_{_norm_label(label) or label}"] = {"label": label, "value": value}
        return data

    for f in defs:
        fid = str(f.get("id") or "")
        label = str(f.get("label") or fid)
        existing = data.get(fid)
        if existing and existing.get("value") not in (None, ""):
            existing["label"] = label
            continue

        matched_key = None
        if label in notes_map:
            matched_key = label
        else:
            for nk in notes_map:
                if _labels_match(label, nk):
                    matched_key = nk
                    break
        if matched_key is not None:
            data[fid] = {"label": label, "value": notes_map[matched_key]}
            used_notes.add(matched_key)

    # If exactly one dynamic field still empty and one notes line unused → assign it
    empty_defs = [
        f
        for f in defs
        if not (data.get(str(f.get("id") or "")) or {}).get("value")
    ]
    unused_notes = {k: v for k, v in notes_map.items() if k not in used_notes}
    if len(empty_defs) == 1 and len(unused_notes) == 1:
        f = empty_defs[0]
        nk, nv = next(iter(unused_notes.items()))
        data[str(f.get("id"))] = {"label": str(f.get("label") or f.get("id")), "value": nv}

    return data


def extra_field_value(item: Any, field_id: str, form_settings: Optional[Dict[str, Any]] = None) -> str:
    data = resolve_member_extra_fields(item, form_settings)
    entry = data.get(field_id)
    if not entry:
        return ""
    val = entry.get("value")
    if val is None or val == "":
        return ""
    if isinstance(val, list):
        return ", ".join(str(x) for x in val)
    return str(val)


async def backfill_extra_fields_from_notes(db, form_settings: Optional[Dict[str, Any]] = None) -> int:
    """Persist notes-derived dynamic values into extra_fields for rows that lack them."""
    from sqlalchemy import select
    from models.registrations import Registrations

    defs = dynamic_field_defs(form_settings)
    if not defs:
        return 0

    result = await db.execute(select(Registrations))
    items = result.scalars().all()
    updated = 0
    for item in items:
        current = loads_extra_fields(getattr(item, "extra_fields", None))
        merged = resolve_member_extra_fields(item, form_settings)
        if merged == current:
            continue
        # only write if we gained something
        if dumps_extra_fields(merged) != dumps_extra_fields(current):
            item.extra_fields = dumps_extra_fields(merged)
            updated += 1
    if updated:
        await db.commit()
        logger.info("Backfilled extra_fields for %s registrations", updated)
    return updated
