"""Local panel authentication helpers (password hashing, seed, schema)."""
import hashlib
import json
import logging
import os
import secrets
from datetime import datetime
from typing import Optional

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.database import Base, db_manager
from models.panel_users import PanelUser

logger = logging.getLogger(__name__)

PERMISSION_KEYS = (
    "view",
    "add",
    "edit",
    "delete",
    "export",
    "manage_users",
    "manage_brand_settings",
    "manage_registration_form_settings",
)


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100_000).hex()
    return f"{salt}${digest}"


def verify_password(password: str, password_hash: str) -> bool:
    try:
        salt, digest = password_hash.split("$", 1)
    except ValueError:
        return False
    check = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100_000).hex()
    return secrets.compare_digest(check, digest)


def default_permissions(all_true: bool = False) -> dict:
    return {key: all_true for key in PERMISSION_KEYS}


def normalize_permissions(raw) -> dict:
    base = default_permissions(False)
    if raw is None:
        return base
    if isinstance(raw, str):
        try:
            raw = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            raw = {}
    if not isinstance(raw, dict):
        return base
    for key in PERMISSION_KEYS:
        if key in raw:
            base[key] = bool(raw[key])
    return base


def permissions_to_json(permissions: dict) -> str:
    return json.dumps(normalize_permissions(permissions), ensure_ascii=False)


_schema_ready = False


async def ensure_schema():
    """Create panel_users / last_modified_by / system_counters if missing."""
    global _schema_ready
    if _schema_ready:
        return
    if not db_manager.engine:
        return
    try:
        # Ensure SystemCounter model is registered on Base.metadata
        from services.membership_numbers import SystemCounter  # noqa: F401
        from models.app_settings import AppSetting  # noqa: F401

        async with db_manager.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

            def _migrate(sync_conn):
                dialect = sync_conn.dialect.name
                # last_modified_by + extra_fields + request_number on registrations
                if dialect == "postgresql":
                    sync_conn.execute(
                        text("ALTER TABLE registrations ADD COLUMN IF NOT EXISTS last_modified_by VARCHAR")
                    )
                    sync_conn.execute(
                        text("ALTER TABLE registrations ADD COLUMN IF NOT EXISTS extra_fields TEXT")
                    )
                    sync_conn.execute(
                        text("ALTER TABLE registrations ADD COLUMN IF NOT EXISTS request_number VARCHAR")
                    )
                elif dialect == "sqlite":
                    rows = sync_conn.execute(text("PRAGMA table_info(registrations)")).fetchall()
                    col_names = {row[1] for row in rows}
                    if "last_modified_by" not in col_names:
                        sync_conn.execute(text("ALTER TABLE registrations ADD COLUMN last_modified_by VARCHAR"))
                    if "extra_fields" not in col_names:
                        sync_conn.execute(text("ALTER TABLE registrations ADD COLUMN extra_fields TEXT"))
                    if "request_number" not in col_names:
                        sync_conn.execute(text("ALTER TABLE registrations ADD COLUMN request_number VARCHAR"))
                else:
                    for col_sql in (
                        "ALTER TABLE registrations ADD COLUMN last_modified_by VARCHAR",
                        "ALTER TABLE registrations ADD COLUMN extra_fields TEXT",
                        "ALTER TABLE registrations ADD COLUMN request_number VARCHAR",
                    ):
                        try:
                            sync_conn.execute(text(col_sql))
                        except Exception:
                            pass

                # unique index on request_number
                try:
                    sync_conn.execute(
                        text(
                            "CREATE UNIQUE INDEX IF NOT EXISTS uq_registrations_request_number "
                            "ON registrations (request_number)"
                        )
                    )
                except Exception as idx_err:
                    logger.warning("Could not ensure unique request_number index: %s", idx_err)

                # Backfill legacy rows missing request_number (REQ-{id:04d}) when free
                try:
                    if dialect == "sqlite":
                        sync_conn.execute(
                            text(
                                "UPDATE registrations SET request_number = printf('REQ-%04d', id) "
                                "WHERE (request_number IS NULL OR request_number = '') "
                                "AND printf('REQ-%04d', id) NOT IN ("
                                "  SELECT request_number FROM registrations "
                                "  WHERE request_number IS NOT NULL AND request_number != ''"
                                ")"
                            )
                        )
                    else:
                        sync_conn.execute(
                            text(
                                "UPDATE registrations SET request_number = "
                                "('REQ-' || lpad(id::text, 4, '0')) "
                                "WHERE (request_number IS NULL OR request_number = '') "
                                "AND ('REQ-' || lpad(id::text, 4, '0')) NOT IN ("
                                "  SELECT request_number FROM registrations "
                                "  WHERE request_number IS NOT NULL AND request_number != ''"
                                ")"
                            )
                        )
                except Exception as bf_err:
                    logger.warning("Could not backfill request_number: %s", bf_err)

                # Normalize empty membership numbers to NULL (needed for UNIQUE)
                try:
                    sync_conn.execute(
                        text("UPDATE registrations SET membership_number = NULL WHERE membership_number = ''")
                    )
                except Exception:
                    pass

                # Unique index on membership_number
                try:
                    if dialect == "sqlite":
                        sync_conn.execute(
                            text(
                                "CREATE UNIQUE INDEX IF NOT EXISTS uq_registrations_membership_number "
                                "ON registrations (membership_number)"
                            )
                        )
                    elif dialect == "postgresql":
                        sync_conn.execute(
                            text(
                                "CREATE UNIQUE INDEX IF NOT EXISTS uq_registrations_membership_number "
                                "ON registrations (membership_number)"
                            )
                        )
                except Exception as idx_err:
                    logger.warning("Could not ensure unique membership_number index: %s", idx_err)

                # Dashboard filter/sort/stats indexes (IF NOT EXISTS — safe on every boot)
                for idx_sql in (
                    "CREATE INDEX IF NOT EXISTS ix_registrations_status ON registrations (status)",
                    "CREATE INDEX IF NOT EXISTS ix_registrations_membership_status "
                    "ON registrations (membership_status)",
                    "CREATE INDEX IF NOT EXISTS ix_registrations_governorate ON registrations (governorate)",
                    "CREATE INDEX IF NOT EXISTS ix_registrations_created_at ON registrations (created_at)",
                    "CREATE INDEX IF NOT EXISTS ix_registrations_status_created_at "
                    "ON registrations (status, created_at)",
                    "CREATE INDEX IF NOT EXISTS ix_registrations_phone ON registrations (phone)",
                ):
                    try:
                        sync_conn.execute(text(idx_sql))
                    except Exception as idx_err:
                        logger.warning("Could not ensure index (%s): %s", idx_sql, idx_err)

                # is_super_admin on panel_users
                if dialect == "sqlite":
                    rows = sync_conn.execute(text("PRAGMA table_info(panel_users)")).fetchall()
                    col_names = {row[1] for row in rows}
                    if "is_super_admin" not in col_names:
                        sync_conn.execute(
                            text("ALTER TABLE panel_users ADD COLUMN is_super_admin BOOLEAN DEFAULT 0")
                        )
                elif dialect == "postgresql":
                    sync_conn.execute(
                        text(
                            "ALTER TABLE panel_users ADD COLUMN IF NOT EXISTS is_super_admin BOOLEAN DEFAULT FALSE"
                        )
                    )

            await conn.run_sync(_migrate)
        _schema_ready = True
    except Exception as e:
        logger.warning(f"Schema ensure skipped/failed: {e}")


async def seed_super_admin(db: Optional[AsyncSession] = None):
    """Create/update Super Admin from env (password never hardcoded)."""
    username = (getattr(settings, "super_admin_username", None) or os.getenv("SUPER_ADMIN_USERNAME") or "").strip()
    password = (getattr(settings, "super_admin_password", None) or os.getenv("SUPER_ADMIN_PASSWORD") or "").strip()

    if not username or not password:
        logger.error(
            "SUPER_ADMIN_USERNAME / SUPER_ADMIN_PASSWORD not set — skipping super admin seed. "
            "Set both on the Railway backend service (Variables) and redeploy so admin login works."
        )
        return

    await ensure_schema()

    async def _seed(session: AsyncSession):
        result = await session.execute(select(PanelUser).where(PanelUser.username == username))
        user = result.scalar_one_or_none()
        perms = permissions_to_json(default_permissions(all_true=True))
        if user:
            user.password_hash = hash_password(password)
            user.permissions = perms
            user.is_active = True
            user.is_super_admin = True
            user.updated_at = datetime.now()
            logger.info("Updated Super Admin user from env: %s", username)
        else:
            user = PanelUser(
                username=username,
                password_hash=hash_password(password),
                permissions=perms,
                is_active=True,
                is_super_admin=True,
                created_at=datetime.now(),
                updated_at=datetime.now(),
            )
            session.add(user)
            logger.info("Created Super Admin user from env: %s", username)
        await session.commit()

    if db is not None:
        await _seed(db)
        return

    if not db_manager.async_session_maker:
        logger.error(
            "Database session maker not ready — cannot seed Super Admin. "
            "Check DATABASE_URL and restart the backend."
        )
        return
    try:
        async with db_manager.async_session_maker() as session:
            await _seed(session)
    except Exception as e:
        logger.error("Super Admin seed failed: %s", e)
