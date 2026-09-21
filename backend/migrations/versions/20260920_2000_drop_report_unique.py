"""drop weekly report unique constraint

Revision ID: 20260920_2000_drop_report_unique
Revises: 20260920_1800_add_report_share
Create Date: 2026-09-20 20:00:00.000000

去掉 weekly_reports 的 (user_id, range_start) 唯一约束，改为普通索引：

需求上允许同一周期存在多份报告——手动「再生成一份新的」时会与已有报告周期重叠，
唯一约束会直接冲突。这里改成一个非唯一索引，并补一个 (user_id, report_type, range_start)
的查询索引，用于「按类型 + 周期锚点查已有报告」的重叠判断。
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260920_2000_drop_report_unique"
down_revision: str | None = "20260920_1800_add_report_share"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    if insp.has_table("weekly_reports"):
        # 旧唯一索引是 create_all 建的，叫 uq_report_user_range_start
        unique_index = "uq_report_user_range_start"
        if unique_index in {i["name"] for i in insp.get_indexes("weekly_reports")}:
            op.drop_index(unique_index, table_name="weekly_reports")
        # 补充按类型 + 周期锚点的查询索引
        existing = {i["name"] for i in insp.get_indexes("weekly_reports")}
        if "idx_report_user_type_start" not in existing:
            op.create_index(
                "idx_report_user_type_start",
                "weekly_reports",
                ["user_id", "report_type", "range_start"],
            )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    if insp.has_table("weekly_reports"):
        existing = {i["name"] for i in insp.get_indexes("weekly_reports")}
        if "idx_report_user_type_start" in existing:
            op.drop_index("idx_report_user_type_start", table_name="weekly_reports")
        if "uq_report_user_range_start" not in existing:
            op.create_unique_constraint(
                "uq_report_user_range_start",
                "weekly_reports",
                ["user_id", "range_start"],
            )