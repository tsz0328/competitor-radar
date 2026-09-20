from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from app.schemas.event import EventRecordOut


class NotificationItemOut(EventRecordOut):
    """一条高优事件通知：复用事件展示字段，附服务端已读态。"""

    is_read: bool = False


class NotificationListOut(BaseModel):
    """通知中心列表：高优事件 + 全局未读数。"""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    records: list[NotificationItemOut] = Field(default_factory=list)
    total: int = 0
    unread: int = 0


class ReadAckOut(BaseModel):
    """标记已读后的轻量回执：只回未读数 + 被标记的事件 id（单条时）。"""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    unread: int = 0
    read_id: int | None = None


class UnreadCountOut(BaseModel):
    """轮询专用：只回未读数，避免每次拉整页。"""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    unread: int = 0
