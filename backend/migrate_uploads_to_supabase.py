"""
Upload existing local backend/uploads files into Supabase Storage bucket `uploads`.

Paths:
  business-images/registrations/*  →  registrations/*
  brand/*                          →  brand/*

Usage (from backend/):
  .\\.venv\\Scripts\\python.exe migrate_uploads_to_supabase.py
"""
from __future__ import annotations

import asyncio
import mimetypes
from pathlib import Path

from dotenv import load_dotenv


async def main() -> int:
    backend = Path(__file__).resolve().parent
    load_dotenv(backend / ".env", override=True)

    from services import supabase_storage as s3store

    if not s3store.configured():
        print("ERROR: set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in backend/.env")
        return 1

    roots = [
        (backend / "uploads" / "business-images" / "registrations", "registrations"),
        (backend / "uploads" / "brand", "brand"),
    ]

    uploaded = 0
    skipped = 0
    failed = 0

    for folder, prefix in roots:
        if not folder.is_dir():
            print(f"skip missing folder: {folder}")
            continue
        for path in sorted(folder.iterdir()):
            if not path.is_file():
                continue
            key = f"{prefix}/{path.name}"
            try:
                data = path.read_bytes()
                ctype = mimetypes.guess_type(path.name)[0]
                await s3store.upload_bytes(key, data, content_type=ctype, upsert=True)
                uploaded += 1
                print(f"OK  {key} ({len(data)} bytes)")
            except Exception as e:
                failed += 1
                print(f"FAIL {key}: {e}")

    print(f"\nDone. uploaded={uploaded} skipped={skipped} failed={failed}")
    return 0 if failed == 0 else 2


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
