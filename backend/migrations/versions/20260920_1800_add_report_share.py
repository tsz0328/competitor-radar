"""add report share token

Revision ID: 20260920_1800_add_report_share
Revises: 20260920_1700_add_competitor_deleted_at
Create Date: 2026-09-20 18:00:00.000000

给 weekly_reports 增加免登录分享字段：
- share_token：分享 token（唯一索引，/api/share/{token} 据此渲染；撤销后清空）
- share_expires_at：过期时间（为空 = 永久有效）
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260920_1800_add_report_share"
down_revision: str | None = "20260920_1700_add_competitor_deleted_at"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    # 开发环境用 create_all 建表，列可能已存在；这里做幂等判断
    if insp.has_table("weekly_reports"):
        columns = {c["name"] for c in insp.get_columns("weekly_reports")}
        if "share_token" not in columns:
            op.add_column(
                "weekly_reports",
                sa.Column("share_token", sa.String(length=64), nullable=True),
            )
            op.create_index(
                "ix_weekly_reports_share_token",
                "weekly_reports",
                ["share_token"],
                unique=True,
            )
        if "share_expires_at" not in columns:
            op.add_column(
                "weekly_reports",
                sa.Column("share_expires_at", sa.DateTime(timezone=True), nullable=True),
            )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    if insp.has_table("weekly_reports"):
        columns = {c["name"] for c in insp.get_columns("weekly_reports")}
        if "share_token" in columns:
            op.drop_index("ix_weekly_reports_share_token", table_name="weekly_reports")
            op.drop_column("weekly_reports", "share_token")
        if "share_expires_at" in columns:
            op.drop_column("weekly_reports", "share_expires_at")