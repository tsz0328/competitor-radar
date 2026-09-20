"""add nickname to users

用户中心：users 新增 nickname 列，存展示用的昵称（与登录账号 username 区分）。
空串表示未设置，界面回退显示账号；不要求唯一。

说明：按 **nullable + 回填** 的方式加列（与 avatar 一致）：
MySQL 的 TEXT/VARCHAR 在加默认值时行为不一致，这里声明 nullable 并由 Python 侧默认值兜底。

Revision ID: f2a3b4c5d6e7
Revises: e6f7a8b9c0d1
Create Date: 2026-09-19 16:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f2a3b4c5d6e7"
down_revision: str | None = "e6f7a8b9c0d1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "nickname" not in [c["name"] for c in inspector.get_columns("users")]:
        op.add_column("users", sa.Column("nickname", sa.String(50), nullable=True))
    op.execute("UPDATE users SET nickname = '' WHERE nickname IS NULL")


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "nickname" in [c["name"] for c in inspector.get_columns("users")]:
        op.drop_column("users", "nickname")
