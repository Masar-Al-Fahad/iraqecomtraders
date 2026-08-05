"""registrations dashboard filter/sort/stats indexes

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-08-05 22:00:00.000000

Also applied at runtime via ensure_schema() (CREATE INDEX IF NOT EXISTS).
Railway/Supabase: restart backend so ensure_schema runs, or:
  alembic upgrade head
"""
from typing import Sequence, Union

from alembic import op


revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, Sequence[str], None] = "c3d4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE INDEX IF NOT EXISTS ix_registrations_status ON registrations (status)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_registrations_membership_status "
        "ON registrations (membership_status)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_registrations_governorate ON registrations (governorate)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_registrations_created_at ON registrations (created_at)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_registrations_status_created_at "
        "ON registrations (status, created_at)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_registrations_status_created_at")
    op.execute("DROP INDEX IF EXISTS ix_registrations_created_at")
    op.execute("DROP INDEX IF EXISTS ix_registrations_governorate")
    op.execute("DROP INDEX IF EXISTS ix_registrations_membership_status")
    op.execute("DROP INDEX IF EXISTS ix_registrations_status")
