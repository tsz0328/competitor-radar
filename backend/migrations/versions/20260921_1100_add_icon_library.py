"""add icon_libraries table

竞品图标库：图标文件托管在后端磁盘（storage_dir/icons），数据库按规范化
域名（小写、去 www）记录一条元信息。管理员上传一次后，该域名下所有竞品
改用后端托管的图标，不再依赖外部站点（Canva 403、docs.qq favicon 返回
HTML 这类"外链失效"问题从此可通过上传修正永久解决）。

双轨兼容：开发期 DB_AUTO_CREATE=true 会先建好表，迁移里先查 has_table，
已存在则跳过（与既有 add_column 类迁移同一口径）。

Revision ID: 20260921_1100_add_icon_library
Revises: 20260920_2000_drop_report_unique
Create Date: 2026-09-21 11:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260921_1100_add_icon_library"
down_revision: str | None = "20260920_2000_drop_report_unique"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("icon_libraries"):
        op.create_table(
            "icon_libraries",
            sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column("domain", sa.String(255), nullable=False, unique=True),
            sa.Column("file_name", sa.String(255), nullable=False),
            sa.Column("content_type", sa.String(100), nullable=False),
            sa.Column("size", sa.Integer(), nullable=False),
            sa.Column("uploaded_by", sa.BigInteger(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
        )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("icon_libraries"):
        op.drop_table("icon_libraries")