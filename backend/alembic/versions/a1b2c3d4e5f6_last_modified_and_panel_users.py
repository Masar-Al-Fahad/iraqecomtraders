"""add last_modified_by and panel_users

Revision ID: a1b2c3d4e5f6
Revises: 2f3e9f3a7ba8
Create Date: 2026-08-03 01:55:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "2f3e9f3a7ba8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("registrations", sa.Column("last_modified_by", sa.String(), nullable=True))
    op.create_table(
        "panel_users",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("username", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=512), nullable=False),
        sa.Column("permissions", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_panel_users_id"), "panel_users", ["id"], unique=False)
    op.create_index(op.f("ix_panel_users_username"), "panel_users", ["username"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_panel_users_username"), table_name="panel_users")
    op.drop_index(op.f("ix_panel_users_id"), table_name="panel_users")
    op.drop_table("panel_users")
    op.drop_column("registrations", "last_modified_by")
