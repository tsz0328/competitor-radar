"""系统级全局设置（键值对）的读写。

目前用于 SMTP 发件配置（5 项）：管理员可在界面覆盖 .env 里的 SMTP_*。
- 库里没值 / 值为空 → 回退 .env（config.get_settings() 对应的 SMTP_* 字段）。
- 库里有值 → 以库为准（界面改完立即生效，无需重启）。

覆盖优先级：库（界面） > .env。只有「授权码」例外——为空表示"不改动"，保留库里已有值。
"""
from sqlalchemy import select

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.models.system_setting import SystemSetting

SENDER_KEY = "smtp_sender"
HOST_KEY = "smtp_host"
PORT_KEY = "smtp_port"
USERNAME_KEY = "smtp_username"
PASSWORD_KEY = "smtp_password"

# 所有可被界面覆盖的 SMTP 字段
SMTP_KEYS = (SENDER_KEY, HOST_KEY, PORT_KEY, USERNAME_KEY, PASSWORD_KEY)


async def get_value(db, key: str, default: str = "") -> str:
    """读一个系统设置；不存在或值为 NULL 时返回 default。"""
    row = (
        await db.execute(select(SystemSetting).where(SystemSetting.key == key))
    ).scalar_one_or_none()
    if row is None or row.value is None:
        return default
    return row.value


async def set_value(db, key: str, value: str) -> None:
    """写入/更新一个系统设置（传空串表示清掉覆盖，回退 .env）。"""
    row = (
        await db.execute(select(SystemSetting).where(SystemSetting.key == key))
    ).scalar_one_or_none()
    if row is None:
        row = SystemSetting(key=key, value=value)
        db.add(row)
    else:
        row.value = value
    await db.commit()


async def get_effective_smtp_config() -> dict:
    """SMTP 实际生效配置：库覆盖优先，否则回退 .env。供通知器在发信时读取。

    返回 host / port / username / password / sender 五项。
    """
    async with SessionLocal() as db:
        host = await get_value(db, HOST_KEY)
        port = await get_value(db, PORT_KEY)
        username = await get_value(db, USERNAME_KEY)
        password = await get_value(db, PASSWORD_KEY)
        sender = await get_value(db, SENDER_KEY)
    s = get_settings()
    return {
        "host": host or s.smtp_host,
        "port": int(port) if port else s.smtp_port,
        "username": username or s.smtp_username,
        "password": password or s.smtp_password,
        "sender": sender or s.smtp_sender,
    }


# 兼容旧调用方
async def get_effective_smtp_sender() -> str:
    """发件邮箱实际生效值：库里覆盖优先，否则回退 .env。"""
    return (await get_effective_smtp_config())["sender"]


async def set_smtp_sender(value: str) -> None:
    """持久化发件邮箱覆盖值。"""
    async with SessionLocal() as db:
        await set_value(db, SENDER_KEY, value)
