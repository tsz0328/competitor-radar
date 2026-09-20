"""add crawl_logs for unified crawl run history

Revision ID: c3d4e5f6a7b8
Revises: ('b7f1c2d9a4e0', 'a1b2c3d4e5f6')
Create Date: 2026-09-18 17:30:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "c3d4e5f6a7b8"
# 顺手把既有分叉（收藏/偏好 与 事件已读）合并，保证从这里开始只剩一条线性历史
down_revision: str | tuple[str, str] | None = ("b7f1c2d9a4e0", "a1b2c3d4e5f6")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "crawl_logs",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("competitor_id", sa.BigInteger(), nullable=False),
        sa.Column("competitor_name", sa.String(length=100), nullable=False),
        sa.Column("source_id", sa.BigInteger(), nullable=True),
        sa.Column("source_name", sa.String(length=100), nullable=False),
        sa.Column("source_type", sa.String(length=30), nullable=False),
        sa.Column("url", sa.String(length=1024), nullable=False),
        sa.Column("trigger", sa.String(length=10), nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column("changed", sa.Boolean(), nullable=False),
        sa.Column("first_time", sa.Boolean(), nullable=False),
        sa.Column("event_created", sa.Boolean(), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_crawl_log_user_time", "crawl_logs", ["user_id", "created_at"], unique=False)
    op.create_index("idx_crawl_log_status", "crawl_logs", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index("idx_crawl_log_status", table_name="crawl_logs")
    op.drop_index("idx_crawl_log_user_time", table_name="crawl_logs")
    op.drop_table("crawl_logs")
