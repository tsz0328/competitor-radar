"""add models to llm_providers for caching upstream model list

供应商从上游获取到的模型列表落库：新增 models 列（JSON 数组字符串）。
编辑供应商时可直接回填下拉选项，不必每次重新请求上游。

Revision ID: c4d5e6f7a8b9
Revises: b2c3d4e5f6a7
Create Date: 2026-09-19 13:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "c4d5e6f7a8b9"
down_revision: str | None = "b2c3d4e5f6a7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 双轨兼容：create_all 先建过列的库直接跳过（开发库热重载）
    inspector = sa.inspect(op.get_bind())
    if "models" not in [c["name"] for c in inspector.get_columns("llm_providers")]:
        op.add_column(
            "llm_providers",
            sa.Column("models", sa.Text(), server_default="", nullable=False),
        )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "models" in [c["name"] for c in inspector.get_columns("llm_providers")]:
        op.drop_column("llm_providers", "models")
