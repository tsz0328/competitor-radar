"""add deleted_at to competitors

竞品删除改为「软删除」（回收站）：
- 加 deleted_at 列（可空、带索引）；非空表示该竞品已移入回收站；
- 删除接口只置标记、不删行，竞品的监控源/快照/事件全部随行保留，
  重加同竞品（按 official_url 命中）可原样恢复，历史数据自动连回；
- 回收站页提供「恢复 / 彻底删除」，超过保留期（30 天）惰性清理。

按双轨兼容写法：开发库若已存在该列则跳过（create_all 热重载场景）。

Revision ID: 20260920_1700_add_competitor_deleted_at
Revises: 20260920_1600_split_account_email
Create Date: 2026-09-20 17:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260920_1700_add_competitor_deleted_at"
down_revision: str | None = "20260920_1600_split_account_email"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = [c["name"] for c in inspector.get_columns("competitors")]
    if "deleted_at" not in columns:
        op.add_column(
            "competitors",
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        )
    existing_indexes = {ix["name"] for ix in inspector.get_indexes("competitors")}
    if "ix_competitors_deleted_at" not in existing_indexes:
        op.create_index("ix_competitors_deleted_at", "competitors", ["deleted_at"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = [c["name"] for c in inspector.get_columns("competitors")]
    if "deleted_at" in columns:
        existing_indexes = {ix["name"] for ix in inspector.get_indexes("competitors")}
        if "ix_competitors_deleted_at" in existing_indexes:
            op.drop_index("ix_competitors_deleted_at", table_name="competitors")
        op.drop_column("competitors", "deleted_at")
