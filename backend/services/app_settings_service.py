"""Brand + registration form settings defaults and persistence."""
from __future__ import annotations

import copy
import json
import logging
from datetime import datetime
from typing import Any, Dict, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.app_settings import AppSetting

logger = logging.getLogger(__name__)

KEY_BRAND = "brand"
KEY_REG_FORM = "registration_form"

DEFAULT_BRAND: Dict[str, Any] = {
    "system_logo": "/brand/mfec-logo.png",
    "report_logo": "/brand/mfec-logo.png",
    "favicon": "/favicon.svg",
    "system_name": "تجمع تجار التجارة الإلكترونية في العراق",
    "company_name": "شركة مسار الفهد للتجارة العامة والنقل العام",
    "org_abbr": "MFEC",
    "primary_color": "#1F2937",
    "secondary_color": "#C89B3C",
    "button_color": "#C89B3C",
    "header_color": "#1F2937",
    "table_header_color": "#1F2937",
    "table_alt_row_color": "#F3F4F6",
    "footer_text": "برعاية شركة مسار الفهد للتجارة العامة والنقل العام",
    "website": "www.masaralfahad.com",
    "email": "management@masaralfahad.com",
    "phone": "07748077716",
    "address": "العراق",
    "header_text": "لوحة إدارة تجمع تجار التجارة الإلكترونية",
    "footer_text_secondary": "تعاون • نمو • فرص • نجاح",
    "report_title": "تقرير أعضاء تجمع تجار التجارة الإلكترونية في العراق",
    "copyright": "© جميع الحقوق محفوظة — تجمع تجار التجارة الإلكترونية في العراق",
    "watermark_enabled": "true",
    "watermark_opacity": "7",
    "whatsapp_welcome_message": (
        "مرحبًا بك في تجمع تجار التجارة الإلكترونية في العراق 🌹\n\n"
        "تمت الموافقة على طلب انضمامك بنجاح، وأصبحت عضوًا في التجمع.\n"
        "رقم عضويتك: {membership_number}\n\n"
        "يمكنك الآن الانضمام إلى كروب الواتساب الرسمي عبر الرابط التالي:\n\n"
        "https://chat.whatsapp.com/K7mtcycs8bBAnryQk3UgLc\n\n"
        "نتمنى لك التوفيق، ونسعد بانضمامك إلى تجمع تجار التجارة الإلكترونية في العراق."
    ),
}

DEFAULT_FORM_FIELDS = [
    {
        "id": "business_name",
        "type": "text",
        "label": "اسم النشاط التجاري",
        "placeholder": "أدخل اسم النشاط التجاري",
        "required": True,
        "visible": True,
        "order": 1,
        "options": [],
        "maps_to": "business_name",
    },
    {
        "id": "merchant_name",
        "type": "text",
        "label": "اسم التاجر",
        "placeholder": "أدخل الاسم الكامل",
        "required": True,
        "visible": True,
        "order": 2,
        "options": [],
        "maps_to": "merchant_name",
    },
    {
        "id": "phone",
        "type": "phone",
        "label": "رقم الهاتف",
        "placeholder": "07XXXXXXXXX",
        "required": True,
        "visible": True,
        "order": 3,
        "options": [],
        "maps_to": "phone",
    },
    {
        "id": "governorate",
        "type": "dropdown",
        "label": "المحافظة",
        "placeholder": "اختر المحافظة",
        "required": True,
        "visible": True,
        "order": 4,
        "options": [
            "بغداد", "البصرة", "نينوى", "أربيل", "النجف", "كربلاء",
            "ذي قار", "بابل", "ديالى", "الأنبار", "كركوك", "صلاح الدين",
            "واسط", "ميسان", "المثنى", "القادسية", "دهوك", "السليمانية",
        ],
        "maps_to": "governorate",
    },
    {
        "id": "area",
        "type": "text",
        "label": "المنطقة / الحي",
        "placeholder": "أدخل المنطقة أو الحي",
        "required": True,
        "visible": True,
        "order": 5,
        "options": [],
        "maps_to": "area",
    },
    {
        "id": "business_type",
        "type": "dropdown",
        "label": "نوع النشاط",
        "placeholder": "اختر نوع النشاط",
        "required": True,
        "visible": True,
        "order": 6,
        "options": [
            "تجارة إلكترونية عامة", "ملابس وأزياء", "إلكترونيات وأجهزة",
            "مواد غذائية", "مستحضرات تجميل وعناية", "أثاث ومفروشات",
            "خدمات رقمية", "تسويق وإعلانات", "تعليم وتدريب",
            "صحة وطب", "سيارات وقطع غيار", "عقارات", "أخرى",
        ],
        "maps_to": "business_type",
    },
    {
        "id": "notes",
        "type": "textarea",
        "label": "ملاحظات",
        "placeholder": "أي معلومات إضافية (اختياري)",
        "required": False,
        "visible": True,
        "order": 7,
        "options": [],
        "maps_to": "notes",
    },
    {
        "id": "image",
        "type": "image_upload",
        "label": "صورة واجهة المتجر / النشاط",
        "placeholder": "",
        "required": True,
        "visible": True,
        "order": 8,
        "options": [],
        "maps_to": "image_key",
    },
    {
        "id": "terms",
        "type": "checkbox",
        "label": "أوافق على شروط الانضمام",
        "placeholder": "",
        "required": True,
        "visible": True,
        "order": 9,
        "options": [],
        "maps_to": None,
    },
]

DEFAULT_REG_FORM: Dict[str, Any] = {
    "identity": {
        "logo": "/brand/mfec-logo.png",
        "title": "طلب انضمام لتجمع تجار التجارة الإلكترونية",
        "subtitle": "املأ البيانات التالية للانضمام إلى تجمع تجار التجارة الإلكترونية في العراق",
        "primary_color": "#1F2937",
        "secondary_color": "#C89B3C",
        "background_color": "#F9FAFB",
        "button_color": "#C89B3C",
        "field_color": "#FFFFFF",
        "logo_size": 72,
        "form_width": 640,
        "border_radius": 12,
        "logo_position": "center",
    },
    "texts": {
        "page_title": "بوابة الانضمام",
        "description": "تجمع تجار التجارة الإلكترونية في العراق — تعاون • نمو • فرص • نجاح",
        "submit_button": "إرسال طلب الانضمام",
        "success_message": "تم استلام طلبك بنجاح",
        "error_message": "حدث خطأ أثناء الإرسال. حاول مرة أخرى.",
        "success_page_title": "تم إرسال الطلب",
        "new_request_button": "إرسال طلب جديد",
    },
    "fields": DEFAULT_FORM_FIELDS,
}


def deep_merge(base: dict, overlay: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (overlay or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


async def get_setting_raw(db: AsyncSession, key: str) -> Optional[AppSetting]:
    result = await db.execute(select(AppSetting).where(AppSetting.key == key))
    return result.scalar_one_or_none()


async def get_brand_settings(db: AsyncSession) -> Dict[str, Any]:
    row = await get_setting_raw(db, KEY_BRAND)
    if not row or not row.value:
        return copy.deepcopy(DEFAULT_BRAND)
    try:
        data = json.loads(row.value)
    except json.JSONDecodeError:
        return copy.deepcopy(DEFAULT_BRAND)
    return deep_merge(DEFAULT_BRAND, data if isinstance(data, dict) else {})


async def get_registration_form_settings(db: AsyncSession) -> Dict[str, Any]:
    row = await get_setting_raw(db, KEY_REG_FORM)
    if not row or not row.value:
        return copy.deepcopy(DEFAULT_REG_FORM)
    try:
        data = json.loads(row.value)
    except json.JSONDecodeError:
        return copy.deepcopy(DEFAULT_REG_FORM)
    merged = deep_merge(DEFAULT_REG_FORM, data if isinstance(data, dict) else {})
    # If custom fields list provided entirely, prefer it (after ensuring list)
    if isinstance(data, dict) and isinstance(data.get("fields"), list) and data["fields"]:
        merged["fields"] = data["fields"]
    return merged


async def save_setting(
    db: AsyncSession,
    key: str,
    value: Dict[str, Any],
    updated_by: str,
) -> Tuple[Dict[str, Any], Optional[str]]:
    """Save setting JSON. Returns (new_value, old_value_json)."""
    row = await get_setting_raw(db, key)
    old_json = row.value if row else None
    new_json = json.dumps(value, ensure_ascii=False)
    if row is None:
        row = AppSetting(
            key=key,
            value=new_json,
            updated_by=updated_by,
            updated_at=datetime.now(),
            created_at=datetime.now(),
        )
        db.add(row)
    else:
        row.value = new_json
        row.updated_by = updated_by
        row.updated_at = datetime.now()
    await db.commit()
    await db.refresh(row)
    return value, old_json
