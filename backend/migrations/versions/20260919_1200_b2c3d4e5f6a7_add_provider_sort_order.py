"""add sort_order to llm_providers for manual drag ordering

供应商列表支持手动拖动排序：新增 sort_order 列，运行时仍只认「使用中」的那一条，
排序仅影响展示顺序。已有记录按创建顺序（id）初始化排序值。

Revision ID: b2c3d4e5f6a7
Revises: a9b8c7d6e5f4
Create Date: 2026-09-19 12:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "b2c3d4e5f6a7"
down_revision: str | None = "a9b8c7d6e5f4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 双轨兼容：create_all 先建过列的库直接跳过（开发库热重载）
    inspector = sa.inspect(op.get_bind())
    if "sort_order" not in [c["name"] for c in inspector.get_columns("llm_providers")]:
        op.add_column(
            "llm_providers",
            sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        )
    # 初始化：保持创建顺序（id 升序），数值越小越靠前
    op.execute("UPDATE llm_providers SET sort_order = id")


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "sort_order" in [c["name"] for c in inspector.get_columns("llm_providers")]:
        op.drop_column("llm_providers", "sort_order")
