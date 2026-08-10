import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest
import sqlalchemy as sa


MIGRATION_PATH = (
    Path(__file__).parents[1]
    / "alembic"
    / "versions"
    / "07c8d9e0f1a2_financial_erp_redesign.py"
)

LEGACY_TABLES = {
    "registrations",
    "financial_companies",
    "financial_company_contracts",
    "financial_member_company_accounts",
    "financial_accounting_periods",
    "financial_monthly_activities",
    "financial_expenses",
}

ERP_TABLES = {
    "financial_company_attachments",
    "financial_pricing_items",
    "financial_pricing_item_versions",
    "financial_member_account_items",
    "financial_member_annexes",
    "financial_monthly_statements",
    "financial_statement_attachments",
    "financial_monthly_entry_lines",
    "financial_settlement_batches",
    "financial_settlement_lines",
    "financial_settlement_reversals",
    "financial_revenue_receipts",
    "financial_receipt_allocations",
}


def load_migration():
    spec = importlib.util.spec_from_file_location("financial_erp_migration_under_test", MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def empty_table():
    return {
        "columns": {},
        "pk": {"name": None, "constrained_columns": []},
        "uniques": [],
        "checks": [],
        "fks": [],
        "indexes": [],
    }


class FakeScalarResult:
    def __init__(self, value):
        self.value = value

    def scalar(self):
        return self.value


class FakeBind:
    def __init__(self):
        self.dialect = SimpleNamespace(
            identifier_preparer=SimpleNamespace(quote=lambda value: f'"{value}"')
        )
        self.queries = []

    def execute(self, statement):
        self.queries.append(str(statement))
        return FakeScalarResult(False)


class FakeInspector:
    def __init__(self, state):
        self.state = state

    def get_table_names(self):
        return list(self.state)

    def get_columns(self, table_name):
        return list(self.state[table_name]["columns"].values())

    def get_pk_constraint(self, table_name):
        return self.state[table_name]["pk"]

    def get_unique_constraints(self, table_name):
        return self.state[table_name]["uniques"]

    def get_check_constraints(self, table_name):
        return self.state[table_name]["checks"]

    def get_foreign_keys(self, table_name):
        return self.state[table_name]["fks"]

    def get_indexes(self, table_name):
        return self.state[table_name]["indexes"]


class FakeOperations:
    def __init__(self, state):
        self.state = state
        self.bind = FakeBind()
        self.ddl = []
        self.seed_sql = []

    def get_bind(self):
        return self.bind

    @staticmethod
    def _column_record(column):
        return {"name": column.name, "type": column.type, "nullable": column.nullable}

    def create_table(self, table_name, *elements):
        self.ddl.append(("create_table", table_name))
        table = sa.Table(table_name, sa.MetaData(), *elements)
        record = empty_table()
        record["columns"] = {
            column.name: self._column_record(column) for column in table.columns
        }
        record["pk"] = {
            "name": table.primary_key.name,
            "constrained_columns": [column.name for column in table.primary_key.columns],
        }
        for constraint in table.constraints:
            if isinstance(constraint, sa.UniqueConstraint):
                record["uniques"].append(
                    {
                        "name": constraint.name,
                        "column_names": [column.name for column in constraint.columns],
                    }
                )
            elif isinstance(constraint, sa.CheckConstraint):
                record["checks"].append(
                    {"name": constraint.name, "sqltext": str(constraint.sqltext)}
                )
        for constraint in table.foreign_key_constraints:
            element = list(constraint.elements)[0]
            record["fks"].append(
                {
                    "name": constraint.name,
                    "constrained_columns": [element.parent.name],
                    "referred_table": element.target_fullname.split(".")[-2],
                    "referred_columns": [element.target_fullname.split(".")[-1]],
                    "options": {"ondelete": element.ondelete} if element.ondelete else {},
                }
            )
        self.state[table_name] = record

    def add_column(self, table_name, column):
        self.ddl.append(("add_column", table_name, column.name))
        self.state[table_name]["columns"][column.name] = self._column_record(column)
        for foreign_key in column.foreign_keys:
            target = foreign_key.target_fullname.split(".")
            self.state[table_name]["fks"].append(
                {
                    "name": None,
                    "constrained_columns": [column.name],
                    "referred_table": target[-2],
                    "referred_columns": [target[-1]],
                    "options": {"ondelete": foreign_key.ondelete} if foreign_key.ondelete else {},
                }
            )

    def create_primary_key(self, name, table_name, columns):
        self.ddl.append(("create_primary_key", table_name, name))
        self.state[table_name]["pk"] = {
            "name": name,
            "constrained_columns": list(columns),
        }

    def create_unique_constraint(self, name, table_name, columns):
        self.ddl.append(("create_unique_constraint", table_name, name))
        self.state[table_name]["uniques"].append(
            {"name": name, "column_names": list(columns)}
        )

    def create_check_constraint(self, name, table_name, sqltext):
        self.ddl.append(("create_check_constraint", table_name, name))
        self.state[table_name]["checks"].append(
            {"name": name, "sqltext": str(sqltext)}
        )

    def create_foreign_key(
        self,
        name,
        source_table,
        referent_table,
        local_cols,
        remote_cols,
        ondelete=None,
    ):
        self.ddl.append(("create_foreign_key", source_table, name))
        self.state[source_table]["fks"].append(
            {
                "name": name,
                "constrained_columns": list(local_cols),
                "referred_table": referent_table,
                "referred_columns": list(remote_cols),
                "options": {"ondelete": ondelete} if ondelete else {},
            }
        )

    def create_index(self, name, table_name, columns, unique=False):
        self.ddl.append(("create_index", table_name, name))
        self.state[table_name]["indexes"].append(
            {"name": name, "column_names": list(columns), "unique": unique}
        )

    def execute(self, statement):
        self.seed_sql.append(str(statement))


@pytest.fixture
def migration_env(monkeypatch):
    migration = load_migration()
    state = {name: empty_table() for name in LEGACY_TABLES}
    operations = FakeOperations(state)
    monkeypatch.setattr(migration, "op", operations)
    monkeypatch.setattr(migration, "_inspector", lambda: FakeInspector(state))
    return migration, operations, state


def test_clean_then_repeated_upgrade_is_ddl_idempotent(migration_env):
    migration, operations, state = migration_env

    migration.upgrade()

    assert ERP_TABLES <= set(state)
    assert len([item for item in operations.ddl if item[0] == "create_table"]) == 13
    assert len([item for item in operations.ddl if item[0] == "add_column"]) == 20
    assert len([item for item in operations.ddl if item[0] == "create_index"]) == 14
    assert len(operations.seed_sql) == 5
    assert all("NOT EXISTS" in statement.upper() for statement in operations.seed_sql)

    operations.ddl.clear()
    migration.upgrade()

    assert operations.ddl == []
    assert len(operations.seed_sql) == 10


def test_partial_schema_upgrade_repairs_missing_compatible_objects(migration_env):
    migration, operations, state = migration_env
    migration.upgrade()

    del state["financial_receipt_allocations"]
    del state["financial_pricing_items"]["columns"]["notes"]
    state["financial_member_account_items"]["indexes"] = [
        item
        for item in state["financial_member_account_items"]["indexes"]
        if item["name"] != "ix_fin_member_account_item_pricing"
    ]
    state["financial_pricing_item_versions"]["checks"] = []
    state["financial_member_annexes"]["fks"] = [
        item
        for item in state["financial_member_annexes"]["fks"]
        if item["constrained_columns"] != ["account_id"]
    ]
    del state["financial_companies"]["columns"]["mobile"]
    operations.ddl.clear()

    migration.upgrade()

    assert ("create_table", "financial_receipt_allocations") in operations.ddl
    assert ("add_column", "financial_pricing_items", "notes") in operations.ddl
    assert ("add_column", "financial_companies", "mobile") in operations.ddl
    assert any(item[0] == "create_index" for item in operations.ddl)
    assert any(item[0] == "create_check_constraint" for item in operations.ddl)
    assert any(item[0] == "create_foreign_key" for item in operations.ddl)

    operations.ddl.clear()
    migration.upgrade()
    assert operations.ddl == []


def test_migration_table_shapes_match_financial_orm(migration_env):
    from core.database import Base
    import models.financial  # noqa: F401

    migration, _operations, state = migration_env
    migration.upgrade()

    for table_name in ERP_TABLES:
        orm_table = Base.metadata.tables[table_name]
        migrated = state[table_name]
        assert set(migrated["columns"]) == {column.name for column in orm_table.columns}
        for column in orm_table.columns:
            actual = migrated["columns"][column.name]
            assert migration._type_signature(actual["type"]) == migration._type_signature(
                column.type
            )
            assert actual["nullable"] == column.nullable

        assert tuple(migrated["pk"]["constrained_columns"]) == tuple(
            column.name for column in orm_table.primary_key.columns
        )
        assert {
            (
                constraint.name,
                tuple(column.name for column in constraint.columns),
            )
            for constraint in orm_table.constraints
            if isinstance(constraint, sa.UniqueConstraint)
        } == {
            (constraint["name"], tuple(constraint["column_names"]))
            for constraint in migrated["uniques"]
        }
        assert {
            constraint.name
            for constraint in orm_table.constraints
            if isinstance(constraint, sa.CheckConstraint)
        } == {constraint["name"] for constraint in migrated["checks"]}
        assert {
            (index.name, tuple(column.name for column in index.columns), index.unique)
            for index in orm_table.indexes
        } == {
            (index["name"], tuple(index["column_names"]), index["unique"])
            for index in migrated["indexes"]
        }


def test_incompatible_existing_column_fails_with_actionable_error(migration_env):
    migration, _operations, state = migration_env
    state["financial_companies"]["columns"]["mobile"] = {
        "name": "mobile",
        "type": sa.Integer(),
        "nullable": True,
    }

    with pytest.raises(RuntimeError, match=r"financial_companies\.mobile.*expected type"):
        migration.upgrade()
