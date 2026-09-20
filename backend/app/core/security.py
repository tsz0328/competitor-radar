from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import get_settings

settings = get_settings()

# 创建一个密码上下文，指定用 bcrypt 算法
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain: str) -> str:
    """把明文密码变成不可逆的哈希串（存数据库用）。"""
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """登录时校验：把用户输入的密码哈希后，与库里的串比对。"""
    return pwd_context.verify(plain, hashed)


def create_access_token(
    subject: str | int, expires_minutes: int | None = None
) -> str:
    """登录成功后签发令牌：把用户 id 塞进令牌里。

    expires_minutes 留空时用配置里的兜底时长；登录 / 注册接口会按「记住我」传具体值，
    见 create_login_token()。
    """
    minutes = expires_minutes or settings.access_token_expire_minutes
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(subject),  # sub=主题，约定放用户标识
        "iat": now,  # 签发时间
        "exp": now + timedelta(minutes=minutes),  # 过期时间
    }
    # 用密钥签名 → 别人改不动内容，一改签名就对不上
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_login_token(subject: str | int, remember: bool) -> str:
    """登录 / 注册专用：按「记住我」选令牌时长。

    勾选 → 长期令牌（默认 30 天），配合前端 localStorage，关浏览器后仍是登录态；
    不勾 → 会话令牌（默认 24 小时），前端只存 sessionStorage，关浏览器即失效。
    """
    minutes = (
        settings.remember_token_expire_minutes
        if remember
        else settings.session_token_expire_minutes
    )
    return create_access_token(subject, minutes)


def decode_access_token(token: str) -> dict | None:
    """校验令牌：签名不对 / 已过期 → 返回 None（而不是抛异常）。"""
    try:
        return jwt.decode(
            token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
        )
    except JWTError:
        return None
