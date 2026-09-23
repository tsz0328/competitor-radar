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


def _norm_action(value: str | None) -> str:
    """把 ondelete 归一化，便于比较。SQLite 把"没写"读作 NO ACTION，视同空。"""
    normalized = (value or "").upper().replace("_", " ").strip()
    return "" if normalized in ("", "NO ACTION", "RESTRICT") else normalized


def _replace_source_foreign_key(table: str, ondelete: str | None) -> None:
    """把 source_id 的外键换成带指定 ondelete 的版本。

    ⚠️ 两处踩过的坑：
    1. **外键可能是匿名的**。由 `create_all` 建出来的表，SQLite 反射出的外键
       `name` 为 None，而 batch 模式必须先有名字才能 drop，否则报
       `ValueError: Constraint must have a name`。所以这里自己反射一遍，
       给匿名外键补上名字，再用 `copy_from` 交给 batch。
    2. **已经符合预期就别重建表**。否则每次 upgrade 都要白重建一次大表
       （page_snapshots 是数据量最大的表）。
    """
    bind = op.get_bind()
    source_fks = [
        fk
        for fk in sa.inspect(bind).get_foreign_keys(table)
        if list(fk.get("constrained_columns") or []) == ["source_id"]
    ]
    if not source_fks:
        return
    if _norm_action((source_fks[0].get("options") or {}).get("ondelete")) == _norm_action(
        ondelete
    ):
        return  # 已是目标语义，跳过

    # 真实外键名：MySQL 下是自动生成的（如 page_snapshots_ibfk_1），不能假设成
    # fk_{table}_source_id，否则 DROP 报 1091；SQLite 反射出来是 None，才用生成名兜底。
    constraint_name = source_fks[0].get("name") or f"fk_{table}_source_id"

    metadata = sa.MetaData()
    reflected = sa.Table(table, metadata, autoload_with=bind)
    targets = [
        fk
        for fk in reflected.foreign_key_constraints
        if [column.name for column in fk.columns] == ["source_id"]
    ]
    if not targets:
        return

    for fk in targets:
        fk.name = constraint_name  # 让 batch 的 drop 能按真实名命中（SQLite 匿名则补名）

    with op.batch_alter_table(table, copy_from=reflected) as batch_op:
        batch_op.drop_constraint(constraint_name, type_="foreignkey")
        batch_op.create_foreign_key(
            constraint_name,
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
    # MySQL 报错 1093：不允许在 DELETE 的 WHERE 子查询里直接引用正被改的表。
    # 先把要保留的 id 取回 Python，再用显式 IN 列表删除（SQLite/MySQL 通用）。
    keepers = (
        bind.execute(
            sa.select(sa.func.min(table.c.id))
            .select_from(table)
            .group_by(table.c.user_id, table.c.range_start)
        )
        .scalars()
        .all()
    )
    if keepers:
        bind.execute(sa.delete(table).where(table.c.id.not_in(keepers)))


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
