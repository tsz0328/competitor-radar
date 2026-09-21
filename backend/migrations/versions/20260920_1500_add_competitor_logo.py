"""add logo_url to competitors

竞品图标改为"抓取时解析一次、落库、全站复用"：
- 抓官网首页时顺手从已下载的 HTML 里解析 <link rel="icon">（零额外请求），
  校验确实是图片后写进 competitors.logo_url；
- 竞品列表 / 情报事件等接口直接返回这个地址，前端不再各自去猜；
- 空串表示还没解析到，响应层会回退成 `https://<域名>/favicon.ico`，
  前端再按 apple-touch-icon → 首字母头像逐级兜底。

按 **nullable + 回填** 的方式加列：MySQL 下 VARCHAR 虽然可以带 DEFAULT，
但保持与 avatar 那次一致的写法，避免不同版本的默认值行为差异。

Revision ID: 20260920_1500_add_competitor_logo
Revises: 20260920_1300_email_as_identity
Create Date: 2026-09-20 15:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260920_1500_add_competitor_logo"
down_revision: str | None = "20260920_1300_email_as_identity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 双轨兼容：create_all 先建过列的库直接跳过（开发库热重载）
    inspector = sa.inspect(op.get_bind())
    if "logo_url" not in [c["name"] for c in inspector.get_columns("competitors")]:
        op.add_column("competitors", sa.Column("logo_url", sa.String(500), nullable=True))
    op.execute("UPDATE competitors SET logo_url = '' WHERE logo_url IS NULL")


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "logo_url" in [c["name"] for c in inspector.get_columns("competitors")]:
        op.drop_column("competitors", "logo_url")
