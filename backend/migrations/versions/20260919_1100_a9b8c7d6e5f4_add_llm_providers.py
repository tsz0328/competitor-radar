"""add llm_providers for multi-provider model settings

设置页支持配置多个模型服务商：新建 llm_providers 表，并把 app_settings 里
旧版「单行存凭证」的非空配置拷成一条「使用中」的供应商，升级后配置不丢。

Revision ID: a9b8c7d6e5f4
Revises: f1a2b3c4d5e6
Create Date: 2026-09-19 11:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "a9b8c7d6e5f4"
down_revision: str | None = "f1a2b3c4d5e6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 双轨兼容：create_all 先建过表的库（开发库热重载）直接跳过建表
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("llm_providers"):
        op.create_table(
            "llm_providers",
            sa.Column("id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), autoincrement=True, nullable=False),
            sa.Column("name", sa.String(length=80), server_default="", nullable=False),
            sa.Column("base_url", sa.String(length=255), nullable=False),
            sa.Column("model", sa.String(length=120), nullable=False),
            sa.Column("api_key", sa.String(length=500), server_default="", nullable=False),
            sa.Column("is_active", sa.Boolean(), server_default=sa.false(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
    # 旧数据迁移：app_settings 里已有完整配置时，拷成一条使用中的供应商。
    # 仅在供应商表为空时拷——create_all 建表的库可能已由服务层惰性迁移拷过，避免重复。
    bind = op.get_bind()
    has_rows = bind.execute(sa.text("SELECT COUNT(*) FROM llm_providers")).scalar()
    if not has_rows:
        op.execute(
            "INSERT INTO llm_providers (name, base_url, model, api_key, is_active, created_at, updated_at) "
            "SELECT '已保存配置', llm_base_url, llm_model, llm_api_key, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP "
            "FROM app_settings WHERE llm_base_url <> '' AND llm_model <> ''"
        )


def downgrade() -> None:
    op.drop_table("llm_providers")
