"""账号标识（账号名 / 邮箱）的共享查询与唯一性约束。

**为什么单独一个模块**：`username` 与 `email` 共享同一个登录命名空间（登录时
`WHERE username = ? OR email = ?`），而数据库的唯一索引只管单列，跨列撞车只能靠
应用层拦。这条规则被三个地方用到——注册（auth）、用户中心改账号（users）、
管理员改账号（admin）。写在三处必然漂移，所以集中在这里，改口径只改这里。

规则一句话：**任何写入 username 或 email 的路径，写之前都必须调用
`assert_identifier_free`。**
"""
import random
import re
import string

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    ERR_IDENTIFIER_CONFLICT,
    ERR_LOGIN_AMBIGUOUS,
    BusinessError,
)
from app.core.validators import ACCOUNT_MAX_LEN, ACCOUNT_MIN_LEN
from app.models.user import User


async def find_by_identifier(db: AsyncSession, value: str) -> User | None:
    """按「账号或邮箱」定位账号。

    - 命中 0 行 → 返回 None（调用方决定报错还是建号）；
    - 命中 1 行 → 返回该账号；
    - 命中 **2 行以上** → 抛 `ERR_LOGIN_AMBIGUOUS`。绝不取第一条：那等于随机会
      登进别人的账号。正常写入路径已挡住跨列撞车，走到这里意味着历史数据或人工改库。
    """
    rows = (
        await db.execute(
            select(User).where((User.username == value) | (User.email == value))
        )
    ).scalars().all()
    if len(rows) > 1:
        raise BusinessError(
            ERR_LOGIN_AMBIGUOUS,
            "该标识对应多个账号，无法确定是哪一个，请联系管理员处理",
            409,
        )
    return rows[0] if rows else None


async def assert_identifier_free(
    db: AsyncSession,
    value: str,
    *,
    exclude_user_id: int | None = None,
) -> None:
    """跨列唯一校验：`value` 不能等于**任何一行**的账号名或邮箱。

    `exclude_user_id` 用于「改自己的资料」：排除自己，否则「保持原值不变」也会被
    判成与自身冲突。
    """
    stmt = select(User.id).where((User.username == value) | (User.email == value))
    if exclude_user_id is not None:
        stmt = stmt.where(User.id != exclude_user_id)
    if (await db.execute(stmt)).first() is not None:
        raise BusinessError(
            ERR_IDENTIFIER_CONFLICT, "该账号或邮箱已被使用，请换一个", 400
        )


async def derive_username_from_email(db: AsyncSession, email: str) -> str:
    """邮箱验证码首次登录自动建号时，从邮箱推导一个「合法且空闲」的账号名。

    规则（与 core/validators 的账号名约束一致）：
    - 取 `@` 前的本地部分，去空格 + 转小写；
    - 只保留 `a-z0-9_-`，其余字符（`.` `+` 等）删除；
    - 截到 30 位；若清洗后不足 3 位，用 `user_` + 6 位随机小写兜底；
    - 通过 `assert_identifier_free` 跨列唯一校验；被占用则追加数字后缀直到空闲。

    这样自动建的账号名**不会含 `@`**，与「账号名禁 `@`」规则、与注册 / 用户中心改账号
    走的 `require_valid_account` / `assert_identifier_free` 完全是同一套口径（不再是例外）。
    """
    local = (email.split("@", 1)[0] if "@" in email else email).strip().lower()
    base = re.sub(r"[^a-z0-9_-]", "", local)[: ACCOUNT_MAX_LEN - 4]
    if len(base) < ACCOUNT_MIN_LEN:
        # 本地部分太短（如 `a@x.com`）或清洗后变空（如 `..@x.com`）：随机兜底，保证合法
        base = "user_" + "".join(random.choices(string.ascii_lowercase, k=6))
        base = base[: ACCOUNT_MAX_LEN - 4]

    candidate = base
    suffix = 1
    while True:
        try:
            await assert_identifier_free(db, candidate)
            return candidate
        except BusinessError as exc:
            if exc.code != ERR_IDENTIFIER_CONFLICT:
                raise
            suffix += 1
            candidate = f"{base}{suffix}"
            # 极端兜底：避免无限循环（理论不会发生，仅作保险）
            if suffix > 9999:
                candidate = f"{base}{random.randint(1000, 9999)}"
                await assert_identifier_free(db, candidate)
                return candidate
