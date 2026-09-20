"""add is_active to users

用户管理：users 新增 is_active 列，用于管理员「停用/启用」账号。
停用后无法登录，已登录会话在下一次请求时被拦截（401 强制重新登录）。
默认值 true（1），存量账号一律视为启用。

Revision ID: b3c4d5e6f7a8
Revises: a1b2c3d4e5f6
Create Date: 2026-09-19 18:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b3c4d5e6f7a8"
down_revision: str | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "is_active" not in [c["name"] for c in inspector.get_columns("users")]:
        op.add_column(
            "users",
            sa.Column(
                "is_active",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            ),
        )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "is_active" in [c["name"] for c in inspector.get_columns("users")]:
        op.drop_column("users", "is_active")
