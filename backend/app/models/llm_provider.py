"""LLM 供应商：设置页可添加多个模型服务商，运行时使用「使用中」的那一条。

与 app_settings 的关系：app_settings 只保留该用户的开关（启用 AI、超时、最小变更行数），
凭证类信息（地址 / 模型 / Key）全部收敛到本表，替换「单行存一份」的旧模型。

**按用户隔离**：每个用户只能看到 / 修改自己的供应商（user_id 归属）。
"""
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, BigIntPK, TimestampMixin


class LlmProvider(Base, TimestampMixin):
    """某个用户配置的一个模型服务商（OpenAI 兼容接口）。"""

    __tablename__ = "llm_providers"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)

    # 归属用户：供应商属于每个用户自己，其它用户不可见
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id"), nullable=False, index=True
    )

    # 展示名，如 DeepSeek / 智谱 GLM；空串表示用户没起名（前端显示「自定义」）
    name: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    base_url: Mapped[str] = mapped_column(String(255), nullable=False)
    model: Mapped[str] = mapped_column(String(120), nullable=False)
    api_key: Mapped[str] = mapped_column(String(500), default="", nullable=False)

    # 运行时只认这一条；任意时刻至多一条为 True
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # 列表展示顺序（前端手动拖动排序）；数值越小越靠前
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # 从上游获取到的模型列表（JSON 数组字符串），编辑时回填下拉选项，
    # 避免每次打开编辑都重新请求上游
    models: Mapped[str] = mapped_column(Text, default="", nullable=False)

    # 最近一次「测试连接」的结果：none=未测试 / ok=通过 / fail=不通过。
    # 编辑供应商（地址/模型/Key 变化）后旧结果作废，重置回 none。
    last_test_status: Mapped[str] = mapped_column(
        String(16), default="none", nullable=False
    )
    last_test_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
