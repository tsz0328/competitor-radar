"""merge heads: 报告软删分支与图标库/管理端增强分支汇合

用户先升级过 20260920_1800_add_report_deleted_at，后又在
20260921_1100_add_icon_library 上开发了 20260921_1200_admin_enhancements，
形成双头。本迁移只负责汇合，没有实际 schema 变更。

Revision ID: 20260921_1300_merge_heads
Revises: 20260920_1800_add_report_deleted_at, 20260921_1200_admin_enhancements
Create Date: 2026-09-21 13:00:00.000000

"""
from collections.abc import Sequence

revision: str = "20260921_1300_merge_heads"
down_revision: str | Sequence[str] | None = (
    "20260920_1800_add_report_deleted_at",
    "20260921_1200_admin_enhancements",
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass