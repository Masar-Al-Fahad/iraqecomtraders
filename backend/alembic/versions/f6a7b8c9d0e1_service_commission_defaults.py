"""editable service commission defaults

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "f6a7b8c9d0e1"
down_revision: Union[str, Sequence[str], None] = "e5f6a7b8c9d0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "financial_service_types",
        sa.Column("default_commission_method", sa.String(40), nullable=True),
    )
    op.add_column(
        "financial_service_types",
        sa.Column("default_commission_value", sa.Numeric(18, 3), nullable=True),
    )
    # Editable database seed values; calculations never hardcode these amounts.
    op.execute(
        """
        UPDATE financial_service_types
        SET default_commission_method = 'fixed_per_operation',
            default_commission_value = 3000
        WHERE code = 'shipping'
        """
    )
    op.execute(
        """
        UPDATE financial_service_types
        SET default_commission_method = 'fixed_per_operation',
            default_commission_value = 500
        WHERE code = 'delivery'
        """
    )


def downgrade() -> None:
    op.drop_column("financial_service_types", "default_commission_value")
    op.drop_column("financial_service_types", "default_commission_method")
