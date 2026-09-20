"""抓取运行日志：把每次抓取的成功/失败/告警统一落库，供「抓取日志」页回溯。

为什么把 competitor_name / user_id 冗余进来、且不加外键：
- 日志是"历史现场"——竞品、监控源之后改名甚至删除，历史记录都不应被改写或连带删除；
- 列表按用户隔离、按时间倒序都走本表冗余列，查询不用 join。

写入点只有一处：analyzer.run_competitor_crawl（手动触发与定时调度共用），
随抓取同事务落库，由调用方决定提交粒度。
"""
from sqlalchemy import BigInteger, Boolean, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, BigIntPK, TimestampMixin

# 触发来源
TRIGGER_MANUAL = "manual"  # 竞品管理页「立即抓取」
TRIGGER_SCHEDULER = "scheduler"  # 定时调度自动抓取

# 抓取状态（与 SourceCrawlOutcome.status 对齐）
STATUS_SUCCESS = "success"
STATUS_FAILED = "failed"
STATUS_SKIPPED = "skipped"

# 日志保留天数：到期的行在下一次抓取落库时顺手清理，避免无限膨胀
RETENTION_DAYS = 30


class CrawlLog(Base, TimestampMixin):
    """一条 = 一个监控源的一次抓取结果。"""

    __tablename__ = "crawl_logs"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)

    # 冗余归属（不设外键：主数据删除后日志仍保留）
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    competitor_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    competitor_name: Mapped[str] = mapped_column(String(100), nullable=False)
    source_id: Mapped[int | None] = mapped_column(BigInteger)
    source_name: Mapped[str] = mapped_column(String(100), nullable=False)
    source_type: Mapped[str] = mapped_column(String(30), nullable=False)
    url: Mapped[str] = mapped_column(String(1024), nullable=False)

    trigger: Mapped[str] = mapped_column(String(10), nullable=False)  # manual / scheduler
    status: Mapped[str] = mapped_column(String(10), nullable=False)  # success / failed / skipped
    http_status: Mapped[int | None] = mapped_column(Integer)
    changed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    first_time: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    event_created: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        Index("idx_crawl_log_user_time", "user_id", "created_at"),
        Index("idx_crawl_log_status", "status"),
    )
