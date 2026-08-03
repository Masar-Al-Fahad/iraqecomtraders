"""membership counter + unique membership_number

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-08-03 03:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("UPDATE registrations SET membership_number = NULL WHERE membership_number = ''")
    op.create_table(
        "system_counters",
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("value", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("name"),
    )
    # Seed counter from max existing MF number (best-effort; app also syncs on startup)
    op.execute(
        """
        INSERT INTO system_counters (name, value)
        SELECT 'membership', COALESCE(MAX(CAST(SUBSTR(membership_number, 4) AS INTEGER)), 0)
        FROM registrations
        WHERE membership_number IS NOT NULL AND membership_number LIKE 'MF-%'
        """
    )
    try:
        op.create_index(
            "uq_registrations_membership_number",
            "registrations",
            ["membership_number"],
            unique=True,
        )
    except Exception:
        pass


def downgrade() -> None:
    try:
        op.drop_index("uq_registrations_membership_number", table_name="registrations")
    except Exception:
        pass
    op.drop_table("system_counters")
