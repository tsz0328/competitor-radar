"""add report favorite and user preferences

Revision ID: b7f1c2d9a4e0
Revises: de562524e257
Create Date: 2026-09-18 10:30:00.000000

把"跟着账号走"的两类数据落库：
- weekly_reports.favorite：周报收藏（原先只存在前端内存/localStorage）
- users.preferences：用户级偏好（原先只存在前端 localStorage）
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'b7f1c2d9a4e0'
down_revision: str | None = 'de562524e257'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    # 开发环境用 create_all 建表，列可能已存在；这里做幂等判断
    if insp.has_table('weekly_reports'):
        columns = {c['name'] for c in insp.get_columns('weekly_reports')}
        if 'favorite' not in columns:
            op.add_column(
                'weekly_reports',
                sa.Column(
                    'favorite',
                    sa.Boolean(),
                    nullable=False,
                    server_default=sa.false(),
                ),
            )

    if insp.has_table('users'):
        columns = {c['name'] for c in insp.get_columns('users')}
        if 'preferences' not in columns:
            op.add_column('users', sa.Column('preferences', sa.JSON(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    if insp.has_table('weekly_reports'):
        columns = {c['name'] for c in insp.get_columns('weekly_reports')}
        if 'favorite' in columns:
            op.drop_column('weekly_reports', 'favorite')

    if insp.has_table('users'):
        columns = {c['name'] for c in insp.get_columns('users')}
        if 'preferences' in columns:
            op.drop_column('users', 'preferences')
