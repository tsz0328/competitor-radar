"""add password_length to users

用户中心：users 新增 password_length 列，仅存「密码位数」（不存明文），
用于在账号页以 * 占位展示密码强度/长度。NULL 表示未知（界面回退"未设置"）。

老账号（注册/改密早于本迁移）为 NULL，改一次密码后即补上。

⚠️ 修订历史：本迁移原 revision id 误用了 `a1b2c3d4e5f6`，与更早的
`20260918_1200_add_event_reads.py` 撞号，导致 alembic 出现 Multiple heads、
`alembic upgrade head` 直接报错（dev 库长期停在 e6f7a8b9c0d1 就是被这个卡住的）。
这里改用唯一 id `d4e5f6a7b8c9`，并同步下游 `b3c4d5e6f7a8` 的 down_revision。

Revision ID: d4e5f6a7b8c9
Revises: f2a3b4c5d6e7
Create Date: 2026-09-19 17:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d4e5f6a7b8c9"
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
