"""Local authentication API (username/password JWT). OIDC/Atoms not required."""
import logging
from datetime import datetime, timezone

from core.auth import create_access_token
from core.config import settings
from core.database import get_db
from dependencies.auth import get_current_user
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from schemas.auth import UserResponse
from services.panel_auth import ensure_schema, verify_password, normalize_permissions, default_permissions
from models.panel_users import PanelUser
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from dependencies.permissions import load_user_permissions

router = APIRouter(prefix="/api/v1/auth", tags=["authentication"])
logger = logging.getLogger(__name__)


class LocalLoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=100)
    password: str = Field(..., min_length=1, max_length=200)


class LocalLoginResponse(BaseModel):
    token: str
    token_type: str = "Bearer"
    user: UserResponse


class PasswordResetRequestIn(BaseModel):
    username: str = Field(..., min_length=1, max_length=100)
    channel: str | None = Field(default=None, description="deprecated")


class PasswordResetConfirmIn(BaseModel):
    username: str = Field(..., min_length=1, max_length=100)
    otp: str = Field(..., min_length=4, max_length=12)
    new_password: str = Field(..., min_length=6, max_length=200)


class BackupCodeResetIn(BaseModel):
    username: str = Field(..., min_length=1, max_length=100)
    code: str = Field(..., min_length=8, max_length=40)
    new_password: str = Field(..., min_length=6, max_length=200)


class SuperAdminRecoveryIn(BaseModel):
    recovery_secret: str = Field(..., min_length=8, max_length=200)
    new_password: str = Field(..., min_length=8, max_length=200)


OTP_DISABLED_DETAIL = (
    "استعادة كلمة المرور عبر OTP/البريد/الهاتف معطّلة. "
    "استخدم رمزًا احتياطيًا من إدارة المستخدمين، أو تواصل مع المدير."
)


def _client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()[:64]
    if request.client:
        return (request.client.host or "")[:64]
    return None


@router.get("/login")
async def login_page_redirect():
    """Redirect browser login to local admin login page (no OIDC)."""
    return RedirectResponse(
        url=f"{settings.frontend_url.rstrip('/')}/admin/login",
        status_code=status.HTTP_302_FOUND,
    )


@router.post("/login", response_model=LocalLoginResponse)
async def local_login(data: LocalLoginRequest, db: AsyncSession = Depends(get_db)):
    """Local username/password login for admin panel."""
    await ensure_schema()
    username = data.username.strip()
    result = await db.execute(select(PanelUser).where(PanelUser.username == username))
    user = result.scalar_one_or_none()

    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="اسم المستخدم أو كلمة المرور غير صحيحة",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="هذا الحساب معطّل. تواصل مع المدير.",
        )

    now = datetime.now(timezone.utc)
    try:
        expires_minutes = int(settings.jwt_expire_minutes)
    except (TypeError, ValueError):
        expires_minutes = 1440

    is_super = bool(getattr(user, "is_super_admin", False))
    perms = default_permissions(all_true=True) if is_super else normalize_permissions(user.permissions)

    claims = {
        "sub": f"panel:{user.id}",
        "email": getattr(user, "email", None) or f"{user.username}@local",
        "name": user.username,
        "role": "admin",
        "username": user.username,
        "is_super_admin": is_super,
        "permissions": perms,
        "last_login": now.isoformat(),
    }
    token = create_access_token(claims, expires_minutes=expires_minutes)

    user_resp = UserResponse(
        id=f"panel:{user.id}",
        email=getattr(user, "email", None) or f"{user.username}@local",
        name=user.username,
        role="admin",
        last_login=now,
        is_super_admin=is_super,
        permissions=perms,
    )

    return LocalLoginResponse(token=token, user=user_resp)


@router.get("/password-reset/status")
async def password_reset_status():
    """OTP delivery disabled — clients should use backup codes."""
    return {
        "otp_enabled": False,
        "backup_codes_enabled": True,
        "email_delivery_available": False,
        "sms_delivery_available": False,
        "dev_echo_enabled": False,
        "message": OTP_DISABLED_DETAIL,
        "required_env": {
            "email": [],
            "sms": [],
            "emergency": ["SUPER_ADMIN_RECOVERY_SECRET"],
            "forbidden_in_production": ["PASSWORD_RESET_DEV_ECHO"],
        },
    }


@router.post("/password-reset/request")
async def password_reset_request(
    data: PasswordResetRequestIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    raise HTTPException(status_code=410, detail=OTP_DISABLED_DETAIL)


@router.post("/password-reset/confirm")
async def password_reset_confirm(
    data: PasswordResetConfirmIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    raise HTTPException(status_code=410, detail=OTP_DISABLED_DETAIL)


@router.post("/password-reset/backup-code")
async def password_reset_with_backup_code(
    data: BackupCodeResetIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    await ensure_schema()
    from services.backup_codes import consume_backup_code_and_reset_password

    return await consume_backup_code_and_reset_password(
        db,
        username=data.username,
        code=data.code,
        new_password=data.new_password,
        request_ip=_client_ip(request),
    )


@router.post("/password-reset/super-admin")
async def password_reset_super_admin(
    data: SuperAdminRecoveryIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Emergency Super Admin reset via SUPER_ADMIN_RECOVERY_SECRET (ops-only)."""
    await ensure_schema()
    from services.password_reset import super_admin_emergency_reset

    return await super_admin_emergency_reset(
        db,
        recovery_secret=data.recovery_secret,
        new_password=data.new_password,
        request_ip=_client_ip(request),
    )


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get current user info with live permissions from DB."""
    perms = await load_user_permissions(db, current_user)
    is_super = bool(getattr(current_user, "is_super_admin", False))
    if current_user.id and str(current_user.id).startswith("panel:"):
        try:
            panel_id = int(str(current_user.id).split(":", 1)[1])
            result = await db.execute(select(PanelUser).where(PanelUser.id == panel_id))
            panel = result.scalar_one_or_none()
            if panel and getattr(panel, "is_super_admin", False):
                is_super = True
                perms = default_permissions(all_true=True)
        except ValueError:
            pass
    return UserResponse(
        id=current_user.id,
        email=current_user.email,
        name=current_user.name,
        role=current_user.role,
        last_login=current_user.last_login,
        is_super_admin=is_super,
        permissions=perms,
    )


@router.post("/logout")
@router.get("/logout")
async def logout():
    """Logout — client discards JWT (no OIDC redirect)."""
    return {"success": True, "message": "تم تسجيل الخروج"}
