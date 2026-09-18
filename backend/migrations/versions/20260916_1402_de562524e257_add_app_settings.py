"""add_app_settings

Revision ID: de562524e257
Revises: 6fb90280d94d
Create Date: 2026-09-16 14:02:20.554178

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = 'de562524e257'
down_revision: str | None = '6fb90280d94d'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    if sa.inspect(bind).has_table('app_settings'):
        return

    op.create_table(
        'app_settings',
        sa.Column('id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), autoincrement=True, nullable=False),
        sa.Column('llm_enabled', sa.Boolean(), nullable=False),
        sa.Column('llm_api_key', sa.String(length=500), nullable=False),
        sa.Column('llm_base_url', sa.String(length=255), nullable=False),
        sa.Column('llm_model', sa.String(length=120), nullable=False),
        sa.Column('llm_timeout_seconds', sa.Float(), nullable=False),
        sa.Column('llm_min_change_lines', sa.Integer(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    bind = op.get_bind()
    if not sa.inspect(bind).has_table('app_settings'):
        return

    op.drop_table('app_settings')
