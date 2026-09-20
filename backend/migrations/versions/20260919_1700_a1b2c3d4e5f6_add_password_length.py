"""add password_length to users

用户中心：users 新增 password_length 列，仅存「密码位数」（不存明文），
用于在账号页以 * 占位展示密码强度/长度。NULL 表示未知（界面回退"未设置"）。

老账号（注册/改密早于本迁移）为 NULL，改一次密码后即补上。

Revision ID: a1b2c3d4e5f6
Revises: f2a3b4c5d6e7
Create Date: 2026-09-19 17:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "f2a3b4c5d6e7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "password_length" not in [c["name"] for c in inspector.get_columns("users")]:
        op.add_column(
            "users", sa.Column("password_length", sa.Integer(), nullable=True)
        )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "password_length" in [c["name"] for c in inspector.get_columns("users")]:
        op.drop_column("users", "password_length")
