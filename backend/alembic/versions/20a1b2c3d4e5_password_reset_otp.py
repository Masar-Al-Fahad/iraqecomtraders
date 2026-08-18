"""Panel user recovery contacts + password_reset_otps table."""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20a1b2c3d4e5"
down_revision: Union[str, Sequence[str], None] = "19e0f1a2b3c4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = set(inspector.get_table_names())

    if "panel_users" in tables:
        columns = {c["name"] for c in inspector.get_columns("panel_users")}
        if "email" not in columns:
            op.add_column("panel_users", sa.Column("email", sa.String(length=255), nullable=True))
        if "phone" not in columns:
            op.add_column("panel_users", sa.Column("phone", sa.String(length=40), nullable=True))
        if "recovery_preferred" not in columns:
            op.add_column("panel_users", sa.Column("recovery_preferred", sa.String(length=20), nullable=True))

    if "password_reset_otps" not in tables:
        op.create_table(
            "password_reset_otps",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("username", sa.String(length=255), nullable=False),
            sa.Column("channel", sa.String(length=20), nullable=False),
            sa.Column("destination_masked", sa.String(length=120), nullable=False, server_default=""),
            sa.Column("code_hash", sa.String(length=128), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="5"),
            sa.Column("request_ip", sa.String(length=64), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("is_consumed", sa.Boolean(), nullable=False, server_default=sa.false()),
        )
        op.create_index("ix_password_reset_otps_username", "password_reset_otps", ["username"])


def downgrade() -> None:
    op.drop_index("ix_password_reset_otps_username", table_name="password_reset_otps")
    op.drop_table("password_reset_otps")
    for col in ("recovery_preferred", "phone", "email"):
        try:
            op.drop_column("panel_users", col)
        except Exception:
            pass
