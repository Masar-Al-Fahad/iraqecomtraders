"""
Migrate all rows from backend/local_app.db (SQLite) → Supabase PostgreSQL.
Preserves primary keys. Skips rows that already exist (by PK).
Does NOT change application logic.

Usage (from backend/):
  .\\.venv\\Scripts\\python.exe migrate_sqlite_to_supabase.py
"""
from __future__ import annotations

import asyncio
import sqlite3
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable, Sequence

from dotenv import load_dotenv

TABLES: list[tuple[str, str]] = [
    # (table_name, primary_key_column)
    ("panel_users", "id"),
    ("registrations", "id"),
    ("app_settings", "id"),
    ("system_counters", "name"),
    ("audit_logs", "id"),
    ("users", "id"),
    ("oidc_states", "id"),
]

BOOL_COLUMNS = {
    "panel_users": {"is_active", "is_super_admin"},
    "registrations": {"whatsapp_registration_sent", "whatsapp_approval_sent"},
}

# Postgres timestamptz columns (SQLite stores these as strings)
DATETIME_COLUMNS = {
    "panel_users": {"created_at", "updated_at"},
    "registrations": {"created_at", "updated_at"},
    "app_settings": {"updated_at", "created_at"},
    "audit_logs": {"created_at"},
    "users": {"created_at", "last_login"},
    "oidc_states": {"expires_at", "created_at"},
}


def _quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _sqlite_rows(db_path: Path, table: str) -> tuple[list[str], list[sqlite3.Row]]:
    con = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        cur = con.execute(f"PRAGMA table_info({table})")
        cols = [r[1] for r in cur.fetchall()]
        rows = list(con.execute(f"SELECT * FROM {table}"))
        return cols, rows
    finally:
        con.close()


def _parse_dt(value: Any) -> Any:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, date) and not isinstance(value, datetime):
        return datetime(value.year, value.month, value.day)
    if isinstance(value, (int, float)):
        # unlikely; leave as-is
        return value
    s = str(value).strip()
    if not s:
        return None
    # Common SQLite formats from this project
    for fmt in (
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d",
    ):
        try:
            return datetime.strptime(s.replace("Z", ""), fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return s


def _normalize_value(table: str, col: str, value: Any) -> Any:
    if value is None:
        return None
    if col in BOOL_COLUMNS.get(table, set()):
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        if isinstance(value, str):
            return value.strip().lower() in ("1", "true", "t", "yes")
    if col in DATETIME_COLUMNS.get(table, set()):
        return _parse_dt(value)
    return value


async def _existing_pks(conn, table: str, pk: str) -> set[Any]:
    rows = await conn.fetch(f"SELECT {_quote_ident(pk)} AS pk FROM {_quote_ident(table)}")
    return {r["pk"] for r in rows}


async def _insert_rows(
    conn,
    table: str,
    cols: Sequence[str],
    rows: Iterable[sqlite3.Row],
    pk: str,
) -> tuple[int, int, int]:
    """Returns (copied, skipped, sqlite_total)."""
    rows_list = list(rows)
    sqlite_total = len(rows_list)
    if sqlite_total == 0:
        return 0, 0, 0

    existing = await _existing_pks(conn, table, pk)
    to_insert: list[dict[str, Any]] = []
    skipped = 0
    for row in rows_list:
        pk_val = row[pk]
        if pk_val in existing:
            skipped += 1
            continue
        to_insert.append({c: _normalize_value(table, c, row[c]) for c in cols})

    if not to_insert:
        return 0, skipped, sqlite_total

    col_sql = ", ".join(_quote_ident(c) for c in cols)
    placeholders = ", ".join(f"${i}" for i in range(1, len(cols) + 1))
    # key is reserved in Postgres — already quoted via _quote_ident
    sql = f"INSERT INTO {_quote_ident(table)} ({col_sql}) VALUES ({placeholders})"

    args = [[rec[c] for c in cols] for rec in to_insert]
    await conn.executemany(sql, args)
    return len(to_insert), skipped, sqlite_total


async def _reset_serial(conn, table: str, pk: str) -> None:
    # Only integer SERIAL tables — skip string PKs (users.id, system_counters.name)
    if table in ("users", "system_counters"):
        return
    seq = await conn.fetchval("SELECT pg_get_serial_sequence($1, $2)", table, pk)
    if not seq:
        return
    await conn.execute(
        f"""
        SELECT setval(
          $1::regclass,
          COALESCE((SELECT MAX({_quote_ident(pk)}) FROM {_quote_ident(table)}), 1),
          true
        )
        """,
        seq,
    )


async def main() -> int:
    backend_dir = Path(__file__).resolve().parent
    load_dotenv(backend_dir / ".env", override=True)

    from core.config import settings

    url = (settings.database_url or "").replace("postgresql+asyncpg://", "postgresql://")
    if not url or "sqlite" in url.lower() or "YOUR_PASSWORD" in url:
        print("ERROR: backend/.env must point to Supabase PostgreSQL")
        return 1

    sqlite_path = backend_dir / "local_app.db"
    if not sqlite_path.exists():
        print(f"ERROR: SQLite DB not found: {sqlite_path}")
        return 1

    import asyncpg

    print("Connecting to Supabase…")
    conn = await asyncpg.connect(url, ssl="require", timeout=30)
    try:
        summary: list[tuple[str, int, int, int, int]] = []
        async with conn.transaction():
            for table, pk in TABLES:
                cols, rows = _sqlite_rows(sqlite_path, table)
                # Only use columns that exist on both sides
                pg_cols = {
                    r["column_name"]
                    for r in await conn.fetch(
                        """
                        SELECT column_name
                        FROM information_schema.columns
                        WHERE table_schema = 'public' AND table_name = $1
                        """,
                        table,
                    )
                }
                use_cols = [c for c in cols if c in pg_cols]
                missing = [c for c in cols if c not in pg_cols]
                if missing:
                    print(f"WARN {table}: SQLite cols missing on PG (ignored): {missing}")

                copied, skipped, total = await _insert_rows(conn, table, use_cols, rows, pk)
                await _reset_serial(conn, table, pk)
                pg_count = await conn.fetchval(f"SELECT COUNT(*) FROM {_quote_ident(table)}")
                summary.append((table, total, copied, skipped, int(pg_count)))
                print(
                    f"{table}: sqlite={total} copied={copied} skipped_existing={skipped} supabase_now={pg_count}"
                )

        print("\n=== VERIFICATION ===")
        ok = True
        for table, sqlite_total, copied, skipped, pg_count in summary:
            match = pg_count >= sqlite_total and (copied + skipped) == sqlite_total
            # After migration, PG count should equal sqlite if started empty or
            # at least contain all sqlite rows (skipped + copied == sqlite)
            status = "OK" if (copied + skipped) == sqlite_total and pg_count >= sqlite_total else "MISMATCH"
            if status != "OK":
                ok = False
            print(
                f"{status} {table}: sqlite={sqlite_total} supabase={pg_count} "
                f"(copied={copied}, skipped={skipped})"
            )
        return 0 if ok else 2
    finally:
        await conn.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
