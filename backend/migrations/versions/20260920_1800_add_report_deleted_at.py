"""add deleted_at to weekly_reports

周报/月报删除改为「软删除」（回收站），与竞品回收站一致：
- 加 deleted_at 列（可空、带索引）；非空表示该报告已移入回收站；
- 删除接口只置标记、不删行，报告内容/分享信息随行保留，可恢复；
- 回收站页提供「恢复 / 彻底删除」，超过保留期（30 天）惰性清理。

按双轨兼容写法：开发库若已存在该列则跳过（create_all 热重载场景）。

Revision ID: 20260920_1800_add_report_deleted_at
Revises: 20260920_1700_add_competitor_deleted_at
Create Date: 2026-09-20 18:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260920_1800_add_report_deleted_at"
down_revision: str | None = "20260920_1700_add_competitor_deleted_at"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = [c["name"] for c in inspector.get_columns("weekly_reports")]
    if "deleted_at" not in columns:
        op.add_column(
            "weekly_reports",
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        )
    existing_indexes = {ix["name"] for ix in inspector.get_indexes("weekly_reports")}
    if "ix_weekly_reports_deleted_at" not in existing_indexes:
        op.create_index(
            "ix_weekly_reports_deleted_at", "weekly_reports", ["deleted_at"]
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = [c["name"] for c in inspector.get_columns("weekly_reports")]
    if "deleted_at" in columns:
        existing_indexes = {ix["name"] for ix in inspector.get_indexes("weekly_reports")}
        if "ix_weekly_reports_deleted_at" in existing_indexes:
            op.drop_index("ix_weekly_reports_deleted_at", table_name="weekly_reports")
        op.drop_column("weekly_reports", "deleted_at")
