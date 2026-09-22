"""admin enhancements: user timestamps, audit log, announcements

三个改动：
1. users 增加 created_at（注册时间，存量行回填当前时间）与
   last_login_at（最近活跃，可空 = 从未登录）；
2. 新增 admin_audit_log 表：管理员操作用户 / 系统设置 / 公告的审计日志；
3. 新增 announcements 表：平台公告（管理员发布，用户端横幅展示）。

双轨兼容：开发期 DB_AUTO_CREATE=true 会先建好新表，迁移里先查 has_table，
已存在则跳过；users 加列用 inspector 判列是否存在（与既有 add_column 类迁移同一口径）。

Revision ID: 20260921_1200_admin_enhancements
Revises: 20260921_1100_add_icon_library
Create Date: 2026-09-21 12:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260921_1200_admin_enhancements"
down_revision: str | None = "20260921_1100_add_icon_library"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _has_column(table: str, column: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return column in {c["name"] for c in inspector.get_columns(table)}


# 与 models/base.py 的 BigIntPK 同口径：SQLite 下主键必须是 INTEGER 才支持自增
_BIGINT_PK = sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def upgrade() -> None:
    # ---- users：注册时间 / 最近活跃 ----
    if not _has_column("users", "created_at"):
        # SQLite 的 ALTER TABLE ADD COLUMN 不允许「非常量默认值 + NOT NULL」；
        # 只能加可空列再加回填（ORM 侧有 Python default 兜底，新插入行也不会空）
        op.add_column(
            "users",
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        )
        # 存量行回填（server_default 只对之后插入的行生效）
        op.execute("UPDATE users SET created_at = CURRENT_TIMESTAMP WHERE created_at IS NULL")
    if not _has_column("users", "last_login_at"):
        op.add_column(
            "users",
            sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        )

    # ---- admin_audit_log ----
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("admin_audit_log"):
        op.create_table(
            "admin_audit_log",
            sa.Column("id", _BIGINT_PK, primary_key=True, autoincrement=True),
            sa.Column("admin_id", sa.BigInteger(), nullable=False),
            sa.Column("admin_username", sa.String(100), nullable=False),
            sa.Column("action", sa.String(64), nullable=False),
            sa.Column("target_type", sa.String(32), nullable=False),
            sa.Column("target_id", sa.BigInteger(), nullable=True),
            sa.Column("detail", sa.Text(), nullable=False, server_default=""),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
        )
        op.create_index("ix_admin_audit_log_action", "admin_audit_log", ["action"])

    # ---- announcements ----
    if not inspector.has_table("announcements"):
        op.create_table(
            "announcements",
            sa.Column("id", _BIGINT_PK, primary_key=True, autoincrement=True),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("created_by", sa.BigInteger(), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
        )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("announcements"):
        op.drop_table("announcements")
    if inspector.has_table("admin_audit_log"):
        op.drop_index("ix_admin_audit_log_action", table_name="admin_audit_log")
        op.drop_table("admin_audit_log")
    if _has_column("users", "last_login_at"):
        op.drop_column("users", "last_login_at")
    if _has_column("users", "created_at"):
        op.drop_column("users", "created_at")