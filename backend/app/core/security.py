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


def create_access_token(subject: str | int) -> str:
    """登录成功后签发令牌：把用户 id 塞进令牌里。"""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(subject),  # sub=主题，约定放用户标识
        "iat": now,  # 签发时间
        "exp": now
        + timedelta(minutes=settings.access_token_expire_minutes),  # 过期时间
    }
    # 用密钥签名 → 别人改不动内容，一改签名就对不上
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict | None:
    """校验令牌：签名不对 / 已过期 → 返回 None（而不是抛异常）。"""
    try:
        return jwt.decode(
            token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
        )
    except JWTError:
        return None
