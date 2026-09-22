"""add test status to llm_providers

供应商列表增加「测试连接」结果标签：新增 last_test_status（none/ok/fail）
与 last_test_at 两列，设置页据此展示「通过 / 未测试 / 不通过」。

Revision ID: 20260921_1400
Revises: 20260921_1300_merge_heads
Create Date: 2026-09-21 14:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260921_1400"
down_revision: str | None = "20260921_1300_merge_heads"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 双轨兼容：create_all 先建过列的库直接跳过（开发库热重载）
    inspector = sa.inspect(op.get_bind())
    cols = {c["name"] for c in inspector.get_columns("llm_providers")}
    if "last_test_status" not in cols:
        op.add_column(
            "llm_providers",
            sa.Column("last_test_status", sa.String(16), server_default="none", nullable=False),
        )
    if "last_test_at" not in cols:
        op.add_column("llm_providers", sa.Column("last_test_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    cols = {c["name"] for c in inspector.get_columns("llm_providers")}
    if "last_test_status" in cols:
        op.drop_column("llm_providers", "last_test_status")
    if "last_test_at" in cols:
        op.drop_column("llm_providers", "last_test_at")
