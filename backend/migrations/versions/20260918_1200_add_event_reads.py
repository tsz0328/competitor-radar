"""add event_reads for server-side notification read state

Revision ID: a1b2c3d4e5f6
Revises: 6fb90280d94d
Create Date: 2026-09-18 12:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = 'a1b2c3d4e5f6'
down_revision: str | None = '6fb90280d94d'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'event_reads',
        sa.Column('id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('event_id', sa.BigInteger(), nullable=False),
        sa.Column('is_read', sa.Boolean(), nullable=False),
        sa.Column('read_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['event_id'], ['intelligence_events.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'event_id', name='uq_event_read_user_event'),
    )
    op.create_index('ix_event_reads_user_id', 'event_reads', ['user_id'], unique=False)
    op.create_index('ix_event_reads_event_id', 'event_reads', ['event_id'], unique=False)


def downgrade() -> None:
    op.drop_table('event_reads')
