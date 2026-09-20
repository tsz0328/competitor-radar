from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.source_registry import SourceType
from app.models.base import Base, BigIntPK, enum_values


class PageSnapshot(Base):
    """一次抓取记录：这次抓到了什么、相比上次有没有变化。

    只为三种情况留痕，不是"每次都写一条"的全量日志：
    1. 首次抓取 —— 建立后续比对的基准
    2. 内容有变化 —— 附带 difflib 差异文本，供里程碑 7 交给 LLM 分析
    3. 抓取失败 —— 记 http_status / fail_reason，便于排查

    内容未变化且成功的抓取只更新 monitor_sources 的健康度字段、不新增记录，
    否则按小时频率抓取会迅速把表撑大（见 docs/data-source-design.md 第八节）。
    """

    __tablename__ = "page_snapshots"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)

    # 归属：查历史时按 competitor 聚合，按 source 定位到"哪个页面变了"
    competitor_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    source_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("monitor_sources.id", ondelete="SET NULL"), nullable=True
    )
    source_type: Mapped[SourceType | None] = mapped_column(
        Enum(SourceType, native_enum=False, length=30, values_callable=enum_values)
    )

    url: Mapped[str] = mapped_column(String(1024), nullable=False)
    # 原始 HTML 落 backend/storage/，库里只存相对路径
    raw_html_path: Mapped[str | None] = mapped_column(String(255))
    clean_text: Mapped[str | None] = mapped_column(Text)  # 清洗后的正文
    content_hash: Mapped[str | None] = mapped_column(String(64), index=True)  # 粗筛是否变化

    http_status: Mapped[int | None] = mapped_column(Integer)
    is_success: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    fail_reason: Mapped[str | None] = mapped_column(Text)

    change_detected: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    diff_text: Mapped[str | None] = mapped_column(Text)

    crawled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("idx_snapshot_competitor_crawled", "competitor_id", "crawled_at"),
        Index("idx_snapshot_source_crawled", "source_id", "crawled_at"),
    )
