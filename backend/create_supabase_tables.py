"""
One-shot: connect to DATABASE_URL (Supabase) and create tables via SQLAlchemy models.
Does NOT migrate/copy data from SQLite.

Usage (from backend/):
  .\\.venv\\Scripts\\python.exe create_supabase_tables.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path


async def main() -> int:
    # Prefer backend/.env over any stale shell DATABASE_URL
    from dotenv import load_dotenv

    env_path = Path(__file__).resolve().parent / ".env"
    load_dotenv(env_path, override=True)

    # Import models / routers so every table is registered on Base.metadata
    from core.config import settings
    from core.database import Base, db_manager

    import models.app_settings  # noqa: F401
    import models.auth  # noqa: F401
    import models.panel_users  # noqa: F401
    import models.registrations  # noqa: F401
    import routers.audit_log  # noqa: F401
    import services.membership_numbers  # noqa: F401

    url = settings.database_url or ""
    if "YOUR_PASSWORD" in url or "YOUR_PROJECT_REF" in url or not url:
        print("ERROR: ضع DATABASE_URL الحقيقي في backend/.env قبل التشغيل.")
        print("المصدر: Supabase → Project Settings → Database → Connection string → URI")
        return 1
    if "sqlite" in url.lower():
        print("ERROR: DATABASE_URL ما زال SQLite. غيّره إلى رابط Supabase PostgreSQL في backend/.env")
        return 1
    if "postgres" not in url.lower():
        print("ERROR: DATABASE_URL لا يبدو رابط PostgreSQL.")
        return 1

    print("Connecting to Supabase PostgreSQL…")
    await db_manager.init_db()
    # Force create even if a previous process marked initialized
    db_manager._initialized = False
    await db_manager.create_tables()

    tables = sorted(Base.metadata.tables.keys())
    print("OK — SQLAlchemy models registered:")
    for name in tables:
        print(f"  - {name}")

    async with db_manager.engine.begin() as conn:
        from sqlalchemy import text

        result = await conn.execute(
            text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public' ORDER BY table_name"
            )
        )
        remote = [r[0] for r in result.fetchall()]
    print("Present in Supabase public schema:")
    for name in remote:
        print(f"  - {name}")

    await db_manager.close_db()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
