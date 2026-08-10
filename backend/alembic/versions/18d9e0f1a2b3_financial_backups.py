"""add private financial backup metadata

Revision ID: 18d9e0f1a2b3
Revises: 07c8d9e0f1a2
"""
from alembic import op
import sqlalchemy as sa

revision = "18d9e0f1a2b3"
down_revision = "07c8d9e0f1a2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("financial_backups"):
        op.create_table(
            "financial_backups",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("backup_number", sa.String(50), nullable=False),
            sa.Column("object_key", sa.String(500), nullable=False),
            sa.Column("kind", sa.String(30), nullable=False, server_default="manual"),
            sa.Column("status", sa.String(30), nullable=False, server_default="ready"),
            sa.Column("notes", sa.Text()),
            sa.Column("size_bytes", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("checksum_sha256", sa.String(64), nullable=False),
            sa.Column("created_by", sa.String(200), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("restore_requested_by", sa.String(200)),
            sa.Column("restore_requested_at", sa.DateTime(timezone=True)),
            sa.Column("pre_restore_backup_id", sa.Integer(), sa.ForeignKey("financial_backups.id", ondelete="SET NULL")),
            sa.Column("deleted_at", sa.DateTime(timezone=True)),
            sa.Column("deleted_by", sa.String(200)),
            sa.UniqueConstraint("backup_number", name="uq_fin_backup_number"),
        )
    inspector = sa.inspect(bind)
    indexes = {idx["name"] for idx in inspector.get_indexes("financial_backups")}
    if "ix_fin_backup_created_status" not in indexes:
        op.create_index("ix_fin_backup_created_status", "financial_backups", ["created_at", "status"])
    if "ix_fin_backup_deleted" not in indexes:
        op.create_index("ix_fin_backup_deleted", "financial_backups", ["deleted_at"])


def downgrade() -> None:
    # Deliberately conservative: backup audit metadata is never dropped automatically.
    pass
