"""通用入参校验（集中一处，避免同一段校验在 auth / users / admin 里各写一遍）。

两套规则，职责不同：
- **邮箱**：够用就好。必须有且仅有一个 @，@ 两侧非空且都不含空白，域名部分带点。
  宁可放宽也不要误杀——一个邮箱是否真的可用，由「验证码能不能收到」来证明，
  正则再严也证明不了这一点。
- **账号名**：收紧，因为它是人自己起的登录标识。3–30 位、只允许 `a-z 0-9 _ -`，
  **明确禁止 `@`**。禁 @ 不是洁癖：账号名与邮箱共享同一个登录命名空间（登录时
  `WHERE username = ? OR email = ?`），禁止账号名长得像邮箱，能把「撞车」的面积
  从根上砍掉一大半。

两者都做「去空格 + 转小写」归一化：`A@X.com` 与 `a@x.com`、`ZhangSan` 与
`zhangsan` 都必须被当成同一个标识，否则用户换个大小写就注册出第二个号。
"""
import re

from app.core.exceptions import (
    ERR_ACCOUNT_INVALID,
    ERR_EMAIL_INVALID,
    BusinessError,
)

# ^本地部分@域名部分.顶级域  且全串无空白
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# 账号名：3–30 位，小写字母 / 数字 / 下划线 / 中划线（归一化后只剩小写）
_ACCOUNT_RE = re.compile(r"^[a-z0-9_-]{3,30}$")

ACCOUNT_MIN_LEN = 3
ACCOUNT_MAX_LEN = 30

# 账号名的规则说明（前后端共用同一句口径，避免提示不一致）
ACCOUNT_RULE_HINT = "账号为 3–30 位，仅可包含字母、数字、下划线或中划线"


def normalize_email(raw: str | None) -> str:
    """统一去空格 + 转小写。"""
    return (raw or "").strip().lower()


def is_valid_email(raw: str | None) -> bool:
    return bool(_EMAIL_RE.match(normalize_email(raw)))


def require_valid_email(raw: str | None) -> str:
    """校验并返回归一化后的邮箱；不合法直接抛业务异常。"""
    email = normalize_email(raw)
    if not is_valid_email(email):
        raise BusinessError(ERR_EMAIL_INVALID, "邮箱格式不正确", 400)
    return email


def normalize_account(raw: str | None) -> str:
    """账号名归一化：去空格 + 转小写。

    只归一化、不校验：登录时对**存量账号**必须宽容（早期可能存过中文名、
    超短名），格式规则只约束「新写入」的账号名，否则一上线就把老账号锁在门外。
    """
    return (raw or "").strip().lower()


def is_valid_account(raw: str | None) -> bool:
    return bool(_ACCOUNT_RE.match(normalize_account(raw)))


def require_valid_account(raw: str | None) -> str:
    """校验并返回归一化后的账号名；不合法直接抛业务异常。"""
    account = normalize_account(raw)
    if not is_valid_account(account):
        raise BusinessError(ERR_ACCOUNT_INVALID, ACCOUNT_RULE_HINT, 400)
    return account


def normalize_identifier(raw: str | None) -> str:
    """登录 / 重置密码时的「账号或邮箱」标识。

    两种标识的归一化规则一致（去空格 + 转小写），所以这里不区分形态；
    登录时**刻意不做任何格式校验**——填错了自然查不到，回一句「账号或密码错误」
    即可，不必告诉对方「你这个格式不对」（那等于免费给出格式探测）。
    """
    return (raw or "").strip().lower()
