"""scope llm settings & providers to user

AI 配置改为按用户隔离：`llm_providers` / `app_settings` 各加一列 `user_id`。

存量数据归属：`MIN(users.id)`（最早注册的用户，通常即管理员/创建者）。
其余用户登录后自行配置自己的供应商即可；他们没有自己的记录时会回退 .env 默认值。

Revision ID: d5e6f7a8b9c0
Revises: c4d5e6f7a8b9
Create Date: 2026-09-19 14:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d5e6f7a8b9c0"
down_revision: str | None = "c4d5e6f7a8b9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _target_user_id() -> str:
    """存量全局配置的归属用户：最早注册的那个（通常就是创建者/管理员）。"""
    uid = op.get_bind().execute(sa.text("SELECT MIN(id) FROM users")).scalar()
    return str(uid or 1)


def upgrade() -> None:
    target = _target_user_id()
    inspector = sa.inspect(op.get_bind())

    # 双轨兼容：create_all 先建过列的库直接跳过（开发库热重载）
    if "user_id" not in [c["name"] for c in inspector.get_columns("llm_providers")]:
        op.add_column(
            "llm_providers",
            sa.Column("user_id", sa.BigInteger(), nullable=False, server_default=target),
        )
        op.create_index("ix_llm_providers_user_id", "llm_providers", ["user_id"])

    if "user_id" not in [c["name"] for c in inspector.get_columns("app_settings")]:
        op.add_column(
            "app_settings",
            sa.Column("user_id", sa.BigInteger(), nullable=False, server_default=target),
        )
        op.create_index(
            "ix_app_settings_user_id", "app_settings", ["user_id"], unique=True
        )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "user_id" in [c["name"] for c in inspector.get_columns("app_settings")]:
        op.drop_index("ix_app_settings_user_id", table_name="app_settings")
        op.drop_column("app_settings", "user_id")
    if "user_id" in [c["name"] for c in inspector.get_columns("llm_providers")]:
        op.drop_index("ix_llm_providers_user_id", table_name="llm_providers")
        op.drop_column("llm_providers", "user_id")
