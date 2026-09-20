"""drop competitor description column

竞品的「一句话描述」字段在界面与后端均已废弃（且后端从未真正落库），
此处把数据库里残留的 competitors.description 列彻底移除。

Revision ID: f1a2b3c4d5e6
Revises: c3d4e5f6a7b8
Create Date: 2026-09-19 10:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "f1a2b3c4d5e6"
down_revision: str | None = "c3d4e5f6a7b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # render_as_batch=True（见 env.py）：SQLite 不支持原生 DROP COLUMN，
    # 批处理模式会自动用「建新表 → 拷贝数据 → 换名」实现，避免手动写兼容 SQL。
    with op.batch_alter_table("competitors") as batch_op:
        batch_op.drop_column("description")


def downgrade() -> None:
    with op.batch_alter_table("competitors") as batch_op:
        batch_op.add_column(sa.Column("description", sa.Text(), nullable=True))
