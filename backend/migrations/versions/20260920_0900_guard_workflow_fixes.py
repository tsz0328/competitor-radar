"""guard workflow consistency fixes

Revision ID: 20260920_0900_guard_workflow_fixes
Revises: b3c4d5e6f7a8
Create Date: 2026-09-20 09:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260920_0900_guard_workflow_fixes"
down_revision: str | None = "b3c4d5e6f7a8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _replace_source_foreign_key(table: str, ondelete: str | None) -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    source_fks = [
        fk
        for fk in inspector.get_foreign_keys(table)
        if list(fk.get("constrained_columns") or []) == ["source_id"]
    ]
    if not source_fks:
        return

    with op.batch_alter_table(table) as batch_op:
        for fk in source_fks:
            batch_op.drop_constraint(fk["name"], type_="foreignkey")
        batch_op.create_foreign_key(
            f"fk_{table}_source_id",
            "monitor_sources",
            ["source_id"],
            ["id"],
            ondelete=ondelete,
        )


def _deduplicate_weekly_reports() -> None:
    bind = op.get_bind()
    table = sa.table(
        "weekly_reports",
        sa.column("id", sa.BigInteger()),
        sa.column("user_id", sa.BigInteger()),
        sa.column("range_start", sa.Date()),
    )
    keepers = (
        sa.select(sa.func.min(table.c.id).label("keep_id"))
        .select_from(table)
        .group_by(table.c.user_id, table.c.range_start)
        .scalar_subquery()
    )
    bind.execute(
        sa.delete(table).where(
            table.c.id.not_in(sa.select(keepers))
        )
    )


def upgrade() -> None:
    _deduplicate_weekly_reports()
    inspector = sa.inspect(op.get_bind())
    existing = {
        tuple(index["column_names"])
        for index in inspector.get_indexes("weekly_reports")
        if index.get("unique")
    }
    if ("user_id", "range_start") not in existing:
        op.create_index(
            "uq_report_user_range_start",
            "weekly_reports",
            ["user_id", "range_start"],
            unique=True,
        )

    _replace_source_foreign_key("page_snapshots", "SET NULL")
    _replace_source_foreign_key("intelligence_events", "SET NULL")


def downgrade() -> None:
    _replace_source_foreign_key("page_snapshots", None)
    _replace_source_foreign_key("intelligence_events", None)

    inspector = sa.inspect(op.get_bind())
    unique_indexes = [
        index
        for index in inspector.get_indexes("weekly_reports")
        if index.get("unique")
        and tuple(index["column_names"]) == ("user_id", "range_start")
    ]
    if unique_indexes:
        op.drop_index("uq_report_user_range_start", table_name="weekly_reports")
