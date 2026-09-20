"""add avatar to users

用户中心：users 新增 avatar 列，存前端裁剪压缩后的头像（data URL），
空串表示还没设置、界面回退成首字母占位头像。

说明：这里按 **nullable + 回填** 的方式加列，而不是 NOT NULL DEFAULT ''：
MySQL 的 TEXT/BLOB 列不允许有默认值，加默认值会直接报 1101；
模型侧仍声明 nullable=False 并由 Python 侧默认值兜底，写入永远是空串。

Revision ID: e6f7a8b9c0d1
Revises: d5e6f7a8b9c0
Create Date: 2026-09-19 15:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e6f7a8b9c0d1"
down_revision: str | None = "d5e6f7a8b9c0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 双轨兼容：create_all 先建过列的库直接跳过（开发库热重载）
    inspector = sa.inspect(op.get_bind())
    if "avatar" not in [c["name"] for c in inspector.get_columns("users")]:
        op.add_column("users", sa.Column("avatar", sa.Text(), nullable=True))
    op.execute("UPDATE users SET avatar = '' WHERE avatar IS NULL")


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "avatar" in [c["name"] for c in inspector.get_columns("users")]:
        op.drop_column("users", "avatar")
