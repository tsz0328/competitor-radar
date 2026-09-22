"""系统级全局设置（键值对）的读写。

目前用于 SMTP 发件配置（5 项）：管理员可在界面覆盖 .env 里的 SMTP_*。
- 库里没值 / 值为空 → 回退 .env（config.get_settings() 对应的 SMTP_* 字段）。
- 库里有值 → 以库为准（界面改完立即生效，无需重启）。

覆盖优先级：库（界面） > .env。只有「授权码」例外——为空表示"不改动"，保留库里已有值。

授权码落库加密：界面保存的 smtp_password 用 Fernet 密文存（前缀 `fernet:`），
密钥取 SMTP_SECRET、留空回退 JWT_SECRET。历史明文兼容：读到无前缀的值按明文
处理，并顺手回写成密文（懒迁移）；改了密钥导致解不开的密文按原文返回
（发信时自然会失败，不会静默发错）。
"""
import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
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

# 密文前缀：有前缀=已加密，无前缀=历史明文
PASSWORD_PREFIX = "fernet:"


def _password_key() -> bytes | None:
    """Fernet 密钥：SMTP_SECRET 优先，留空回退 JWT_SECRET；两者都空返回 None。"""
    s = get_settings()
    secret = (s.smtp_secret or s.jwt_secret or "").strip()
    if not secret:
        return None
    # Fernet 要求 32 字节 urlsafe base64；用 sha256 把任意长度密钥规整化
    return base64.urlsafe_b64encode(hashlib.sha256(secret.encode("utf-8")).digest())


def encrypt_smtp_password(value: str) -> str:
    """明文授权码 → 密文（无密钥时原样返回，保底可发信）。"""
    if not value:
        return value
    key = _password_key()
    if key is None:
        return value
    return PASSWORD_PREFIX + Fernet(key).encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_smtp_password(value: str) -> str:
    """密文 → 明文。无前缀的历史明文原样返回；解不开（改过密钥）也原样返回。"""
    if not value or not value.startswith(PASSWORD_PREFIX):
        return value
    key = _password_key()
    if key is None:
        return value
    try:
        return Fernet(key).decrypt(value[len(PASSWORD_PREFIX):].encode("ascii")).decode("utf-8")
    except InvalidToken:
        return value


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

    返回 host / port / username / password / sender 五项；password 恒为明文
    （历史明文懒迁移成密文，密文读时解密）。
    """
    async with SessionLocal() as db:
        host = await get_value(db, HOST_KEY)
        port = await get_value(db, PORT_KEY)
        username = await get_value(db, USERNAME_KEY)
        password = await get_value(db, PASSWORD_KEY)
        sender = await get_value(db, SENDER_KEY)
        if password and not password.startswith(PASSWORD_PREFIX):
            # 历史明文：顺手回写密文（下一次读就直接走解密路径）
            await set_value(db, PASSWORD_KEY, encrypt_smtp_password(password))
        else:
            password = decrypt_smtp_password(password)
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
