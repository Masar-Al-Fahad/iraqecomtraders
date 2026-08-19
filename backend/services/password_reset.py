"""Forgot-password OTP: short-lived, one-time, rate-limited, no user enumeration."""
from __future__ import annotations

import hashlib
import logging
import os
import random
import smtplib
import ssl
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from typing import Any
from urllib import error as urlerror
from urllib import request as urlrequest

from fastapi import HTTPException
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.panel_users import PanelUser
from models.password_reset import PasswordResetOtp
from services.financial import add_audit
from services.panel_auth import hash_password

logger = logging.getLogger(__name__)

OTP_TTL_MINUTES = 10
MAX_REQUESTS_PER_USER_15M = 3
MAX_REQUESTS_PER_IP_HOUR = 12
MAX_VERIFY_ATTEMPTS = 5
GENERIC_OK = "إن وُجد حساب مرتبط ببيانات الاسترداد، سيتم إرسال رمز التحقق إن كانت القناة مفعّلة."

# Captured in debug/test so integration tests can verify without SMTP.
_LAST_OTP_PLAIN: dict[str, str] = {}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _hash_code(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def _mask_email(value: str) -> str:
    local, _, domain = value.partition("@")
    if not domain:
        return "***"
    keep = local[:2] if len(local) > 2 else local[:1]
    return f"{keep}***@{domain}"


def _mask_phone(value: str) -> str:
    digits = "".join(ch for ch in value if ch.isdigit())
    if len(digits) < 4:
        return "***"
    return f"***{digits[-4:]}"


def _smtp_configured() -> bool:
    return bool(os.getenv("SMTP_HOST") and os.getenv("SMTP_FROM"))


def _sms_configured() -> bool:
    return bool(os.getenv("SMS_WEBHOOK_URL"))


def delivery_status() -> dict[str, Any]:
    """Public, non-enumerating system readiness for OTP channels."""
    return {
        "email_delivery_available": _smtp_configured(),
        "sms_delivery_available": _sms_configured(),
        "otp_ttl_minutes": OTP_TTL_MINUTES,
        "max_verify_attempts": MAX_VERIFY_ATTEMPTS,
        "dev_echo_enabled": os.getenv("PASSWORD_RESET_DEV_ECHO", "").lower() in {"1", "true", "yes"},
        "super_admin_recovery_configured": bool((os.getenv("SUPER_ADMIN_RECOVERY_SECRET") or "").strip()),
        "message": (
            "قنوات الإرسال تعتمد على إعدادات الخادم. "
            "البريد يحتاج SMTP_* والهاتف يحتاج SMS_WEBHOOK_URL."
        ),
    }


def _send_email(to_addr: str, subject: str, body: str) -> None:
    host = os.getenv("SMTP_HOST", "")
    port = int(os.getenv("SMTP_PORT", "587"))
    user = os.getenv("SMTP_USER", "")
    password = os.getenv("SMTP_PASSWORD", "")
    from_addr = os.getenv("SMTP_FROM", "")
    use_tls = os.getenv("SMTP_TLS", "true").lower() not in {"0", "false", "no"}
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg.set_content(body)
    context = ssl.create_default_context()
    with smtplib.SMTP(host, port, timeout=20) as server:
        if use_tls:
            server.starttls(context=context)
        if user:
            server.login(user, password)
        server.send_message(msg)


def _send_sms(to_phone: str, body: str) -> None:
    webhook = os.getenv("SMS_WEBHOOK_URL", "")
    token = os.getenv("SMS_WEBHOOK_TOKEN", "")
    payload = f'{{"to":"{to_phone}","message":"{body}"}}'.encode("utf-8")
    req = urlrequest.Request(
        webhook,
        data=payload,
        headers={
            "Content-Type": "application/json",
            **({"Authorization": f"Bearer {token}"} if token else {}),
        },
        method="POST",
    )
    try:
        with urlrequest.urlopen(req, timeout=15) as resp:
            if getattr(resp, "status", 200) >= 400:
                raise RuntimeError(f"SMS webhook status {resp.status}")
    except urlerror.URLError as err:
        raise RuntimeError(str(err)) from err


async def _rate_limit(db: AsyncSession, username: str, ip: str | None) -> None:
    now = _utcnow()
    since_user = now - timedelta(minutes=15)
    since_ip = now - timedelta(hours=1)
    user_count = (await db.execute(
        select(func.count(PasswordResetOtp.id)).where(
            PasswordResetOtp.username == username,
            PasswordResetOtp.created_at >= since_user,
        )
    )).scalar_one()
    if int(user_count or 0) >= MAX_REQUESTS_PER_USER_15M:
        raise HTTPException(429, "تجاوزت الحد المسموح لطلبات الاستعادة. حاول لاحقًا.")
    if ip:
        ip_count = (await db.execute(
            select(func.count(PasswordResetOtp.id)).where(
                PasswordResetOtp.request_ip == ip,
                PasswordResetOtp.created_at >= since_ip,
            )
        )).scalar_one()
        if int(ip_count or 0) >= MAX_REQUESTS_PER_IP_HOUR:
            raise HTTPException(429, "تجاوزت الحد المسموح من هذا العنوان. حاول لاحقًا.")


def _pick_channel(user: PanelUser, requested: str | None) -> tuple[str, str] | None:
    preferred = (requested or getattr(user, "recovery_preferred", None) or "auto").lower()
    email = (getattr(user, "email", None) or "").strip()
    phone = (getattr(user, "phone", None) or "").strip()
    if preferred == "email" and email:
        return "email", email
    if preferred == "phone" and phone:
        return "phone", phone
    if preferred in {"auto", ""}:
        if email and _smtp_configured():
            return "email", email
        if phone and _sms_configured():
            return "phone", phone
        if email:
            return "email", email
        if phone:
            return "phone", phone
    if preferred == "email" and not email:
        return None
    if preferred == "phone" and not phone:
        return None
    return None


async def request_password_reset(
    db: AsyncSession,
    *,
    username: str,
    channel: str | None = None,
    request_ip: str | None = None,
) -> dict[str, Any]:
    username = (username or "").strip()
    if not username:
        raise HTTPException(400, "اسم المستخدم مطلوب")
    await _rate_limit(db, username, request_ip)

    user = (await db.execute(select(PanelUser).where(PanelUser.username == username))).scalar_one_or_none()
    # Always return generic OK to avoid enumeration — but still rate-limit by username.
    if not user or not user.is_active:
        add_audit(
            db, action="password_reset.request_unknown", entity_type="panel_user", entity_id=None,
            actor=username, new_values={"ip": request_ip},
        )
        await db.commit()
        return {"ok": True, "message": GENERIC_OK}

    picked = _pick_channel(user, channel)
    if not picked:
        add_audit(
            db, action="password_reset.no_channel", entity_type="panel_user", entity_id=user.id,
            actor=username, new_values={"ip": request_ip},
        )
        await db.commit()
        return {"ok": True, "message": GENERIC_OK}

    ch, destination = picked
    if ch == "email" and not _smtp_configured() and os.getenv("PASSWORD_RESET_DEV_ECHO", "").lower() not in {"1", "true", "yes"}:
        # Without SMTP in production, do not pretend delivery succeeded for email.
        if os.getenv("ENVIRONMENT", "dev").lower() in {"prod", "production"}:
            add_audit(
                db, action="password_reset.smtp_missing", entity_type="panel_user", entity_id=user.id,
                actor=username, new_values={"channel": ch},
            )
            await db.commit()
            return {"ok": True, "message": GENERIC_OK}
    if ch == "phone" and not _sms_configured() and os.getenv("PASSWORD_RESET_DEV_ECHO", "").lower() not in {"1", "true", "yes"}:
        if os.getenv("ENVIRONMENT", "dev").lower() in {"prod", "production"}:
            add_audit(
                db, action="password_reset.sms_missing", entity_type="panel_user", entity_id=user.id,
                actor=username, new_values={"channel": ch},
            )
            await db.commit()
            return {"ok": True, "message": GENERIC_OK}

    code = f"{random.randint(0, 999999):06d}"
    now = _utcnow()
    row = PasswordResetOtp(
        username=username,
        channel=ch,
        destination_masked=_mask_email(destination) if ch == "email" else _mask_phone(destination),
        code_hash=_hash_code(code),
        expires_at=now + timedelta(minutes=OTP_TTL_MINUTES),
        attempts=0,
        max_attempts=MAX_VERIFY_ATTEMPTS,
        request_ip=request_ip,
        created_at=now,
        is_consumed=False,
    )
    db.add(row)
    await db.flush()

    body = (
        f"رمز استعادة كلمة المرور: {code}\n"
        f"صالح لمدة {OTP_TTL_MINUTES} دقائق. استخدمه مرة واحدة فقط.\n"
        "إذا لم تطلب الاستعادة فتجاهل هذه الرسالة."
    )
    delivered = False
    try:
        if ch == "email" and _smtp_configured():
            _send_email(destination, "رمز استعادة كلمة المرور", body)
            delivered = True
        elif ch == "phone" and _sms_configured():
            _send_sms(destination, body)
            delivered = True
    except Exception as err:
        logger.warning("password reset delivery failed: %s", err)
        add_audit(
            db, action="password_reset.delivery_failed", entity_type="panel_user", entity_id=user.id,
            actor=username, new_values={"channel": ch, "error": str(err)[:200]},
        )
        await db.commit()
        return {"ok": True, "message": GENERIC_OK}

    if os.getenv("PASSWORD_RESET_DEV_ECHO", "").lower() in {"1", "true", "yes"} or (
        not delivered and os.getenv("ENVIRONMENT", "dev").lower() not in {"prod", "production"}
    ):
        _LAST_OTP_PLAIN[username] = code
        delivered = True

    add_audit(
        db, action="password_reset.requested", entity_type="panel_user", entity_id=user.id,
        actor=username,
        new_values={"channel": ch, "masked": row.destination_masked, "delivered": delivered, "ip": request_ip},
    )
    await db.commit()
    out: dict[str, Any] = {
        "ok": True,
        "message": GENERIC_OK,
        "channel": ch,
        "destination_masked": row.destination_masked,
        "expires_in_minutes": OTP_TTL_MINUTES,
    }
    if os.getenv("PASSWORD_RESET_DEV_ECHO", "").lower() in {"1", "true", "yes"}:
        out["dev_otp"] = code
    return out


async def confirm_password_reset(
    db: AsyncSession,
    *,
    username: str,
    otp: str,
    new_password: str,
    request_ip: str | None = None,
) -> dict[str, Any]:
    username = (username or "").strip()
    otp = (otp or "").strip()
    if not username or not otp:
        raise HTTPException(400, "اسم المستخدم ورمز التحقق مطلوبان")
    if len(new_password or "") < 6:
        raise HTTPException(400, "كلمة المرور الجديدة يجب ألا تقل عن 6 أحرف")

    user = (await db.execute(select(PanelUser).where(PanelUser.username == username))).scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(400, "رمز التحقق غير صالح أو منتهي")

    now = _utcnow()
    row = (await db.execute(
        select(PasswordResetOtp).where(
            PasswordResetOtp.username == username,
            PasswordResetOtp.is_consumed.is_(False),
            PasswordResetOtp.used_at.is_(None),
            PasswordResetOtp.expires_at >= now,
        ).order_by(PasswordResetOtp.id.desc()).limit(1)
    )).scalar_one_or_none()
    if not row:
        raise HTTPException(400, "رمز التحقق غير صالح أو منتهي")

    if int(row.attempts or 0) >= int(row.max_attempts or MAX_VERIFY_ATTEMPTS):
        raise HTTPException(429, "تجاوزت محاولات التحقق. اطلب رمزًا جديدًا.")

    if row.code_hash != _hash_code(otp):
        row.attempts = int(row.attempts or 0) + 1
        add_audit(
            db, action="password_reset.otp_invalid", entity_type="panel_user", entity_id=user.id,
            actor=username, new_values={"attempts": row.attempts, "ip": request_ip},
        )
        await db.commit()
        raise HTTPException(400, "رمز التحقق غير صالح أو منتهي")

    row.is_consumed = True
    row.used_at = now
    user.password_hash = hash_password(new_password)
    user.updated_at = now
    # Invalidate any other open OTPs for this user
    others = (await db.execute(
        select(PasswordResetOtp).where(
            and_(
                PasswordResetOtp.username == username,
                PasswordResetOtp.id != row.id,
                PasswordResetOtp.is_consumed.is_(False),
            )
        )
    )).scalars().all()
    for other in others:
        other.is_consumed = True
        other.used_at = now

    add_audit(
        db, action="password_reset.completed", entity_type="panel_user", entity_id=user.id,
        actor=username, new_values={"ip": request_ip, "channel": row.channel},
    )
    await db.commit()
    _LAST_OTP_PLAIN.pop(username, None)
    return {"ok": True, "message": "تم تحديث كلمة المرور بنجاح. يمكنك تسجيل الدخول الآن."}


async def super_admin_emergency_reset(
    db: AsyncSession,
    *,
    recovery_secret: str,
    new_password: str,
    request_ip: str | None = None,
) -> dict[str, Any]:
    expected = (os.getenv("SUPER_ADMIN_RECOVERY_SECRET") or "").strip()
    if not expected or recovery_secret != expected:
        add_audit(
            db, action="password_reset.super_admin_denied", entity_type="panel_user", entity_id=None,
            actor="system", new_values={"ip": request_ip},
        )
        await db.commit()
        raise HTTPException(403, "رفض طلب الاستعادة الطارئة")
    if len(new_password or "") < 8:
        raise HTTPException(400, "كلمة مرور Super Admin يجب ألا تقل عن 8 أحرف")
    user = (await db.execute(
        select(PanelUser).where(PanelUser.is_super_admin.is_(True)).order_by(PanelUser.id.asc()).limit(1)
    )).scalar_one_or_none()
    if not user:
        raise HTTPException(404, "لا يوجد حساب Super Admin")
    user.password_hash = hash_password(new_password)
    user.updated_at = _utcnow()
    add_audit(
        db, action="password_reset.super_admin_emergency", entity_type="panel_user", entity_id=user.id,
        actor="recovery_secret", new_values={"ip": request_ip},
    )
    await db.commit()
    return {"ok": True, "message": "تم تحديث كلمة مرور Super Admin. غيّر SUPER_ADMIN_RECOVERY_SECRET بعد الاستخدام."}


def peek_dev_otp(username: str) -> str | None:
    return _LAST_OTP_PLAIN.get(username)
