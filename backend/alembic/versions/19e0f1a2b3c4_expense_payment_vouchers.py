"""Add PAY voucher fields on financial_expenses (REC already uses receipt_number)."""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "19e0f1a2b3c4"
down_revision: Union[str, Sequence[str], None] = "18d9e0f1a2b3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = set(inspector.get_table_names())
    if "financial_expenses" not in tables:
        return
    columns = {c["name"] for c in inspector.get_columns("financial_expenses")}
    if "payment_number" not in columns:
        op.add_column("financial_expenses", sa.Column("payment_number", sa.String(length=80), nullable=True))
    if "payee" not in columns:
        op.add_column("financial_expenses", sa.Column("payee", sa.String(length=200), nullable=True))
    if "person_name" not in columns:
        op.add_column("financial_expenses", sa.Column("person_name", sa.String(length=200), nullable=True))
    if "company_name" not in columns:
        op.add_column("financial_expenses", sa.Column("company_name", sa.String(length=200), nullable=True))
    if "payment_method" not in columns:
        op.add_column("financial_expenses", sa.Column("payment_method", sa.String(length=80), nullable=True))

    expenses = conn.execute(
        sa.text("SELECT id FROM financial_expenses WHERE payment_number IS NULL ORDER BY id")
    ).fetchall()
    for (expense_id,) in expenses:
        conn.execute(
            sa.text("UPDATE financial_expenses SET payment_number = :num WHERE id = :id"),
            {"num": f"PAY-LEGACY-{expense_id}", "id": expense_id},
        )

    indexes = {ix["name"] for ix in inspector.get_indexes("financial_expenses")}
    if "uq_fin_expense_payment_number" not in indexes:
        op.create_index("uq_fin_expense_payment_number", "financial_expenses", ["payment_number"], unique=True)


def downgrade() -> None:
    op.drop_index("uq_fin_expense_payment_number", table_name="financial_expenses")
    for col in ("payment_method", "company_name", "person_name", "payee", "payment_number"):
        try:
            op.drop_column("financial_expenses", col)
        except Exception:
            pass
