"""Add hashed panel_user_backup_codes table (OTP table kept for Alembic history).

Revision ID: 21b2c3d4e5f6
Revises: 20a1b2c3d4e5
"""

from alembic import op
import sqlalchemy as sa


revision = "21b2c3d4e5f6"
down_revision = "20a1b2c3d4e5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "panel_user_backup_codes",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("panel_users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("batch_id", sa.String(length=36), nullable=False),
        sa.Column("code_hash", sa.String(length=200), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("used_at", sa.DateTime(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.Column("created_by", sa.String(length=120), nullable=True),
    )
    op.create_index("ix_panel_user_backup_codes_user_id", "panel_user_backup_codes", ["user_id"])
    op.create_index("ix_panel_user_backup_codes_batch_id", "panel_user_backup_codes", ["batch_id"])


def downgrade() -> None:
    op.drop_index("ix_panel_user_backup_codes_batch_id", table_name="panel_user_backup_codes")
    op.drop_index("ix_panel_user_backup_codes_user_id", table_name="panel_user_backup_codes")
    op.drop_table("panel_user_backup_codes")
