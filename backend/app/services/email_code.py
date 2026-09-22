"""邮箱验证码（登录 / 重置密码共用）。

为什么要单独一个模块：
- 「登录」和「重置密码」两条流程都要发码 + 校验，逻辑必须完全一致（同样的有效期、
  同样的限流、同样的场景隔离），否则很容易出现「重置密码拿到的码能直接拿去登录」
  这类漏洞。集中在一处，改口径只改这里。
- 存取走 `core.cache`：`CACHE_BACKEND=memory` 时验证码在进程内（重启即失效，开发可接受）；
  切到 `redis` 后多副本共享，不会出现「A 实例发的码，B 实例验不过」。

安全取舍（写清楚，方便日后收紧）：
- 验证码只存明文（6 位数字、默认 300 秒有效、有次数上限）。缓存不是面向用户的存储，
  能读到缓存就等于能读到码——以「个人自用工具」的定位这是可接受的取舍。
- **校验成功即删除**（一次性使用）；校验失败不消费，但累计失败次数，超过上限直接作废该码，
  避免 6 位数字被暴力枚举。
- **场景隔离**：缓存 key 带 scene，登录码与重置码互不通用。
- **限流两道**：同一个邮箱的重发间隔（默认 60 秒）+ 每小时上限（默认 10 次）。
"""
import logging
import secrets
from datetime import datetime

from app.core.cache import get_cache
from app.core.config import get_settings
from app.core.exceptions import (
    ERR_EMAIL_CODE_INVALID,
    ERR_EMAIL_CODE_TOO_FREQUENT,
    ERR_EMAIL_SEND_FAILED,
    BusinessError,
)
from app.services import notifier

logger = logging.getLogger(__name__)
settings = get_settings()

# 场景：登录（含"验证码即注册"）/ 重置密码
SCENE_LOGIN = "login"
SCENE_RESET = "reset"

# 同一个验证码允许的最大校验失败次数，超过即作废该码（防暴力枚举）
MAX_VERIFY_ATTEMPTS = 5


def _norm(email: str) -> str:
    """统一小写去空格：避免 `A@x.com` 与 `a@x.com` 被当成两个邮箱。"""
    return email.strip().lower()


def _code_key(scene: str, email: str) -> str:
    return f"email_code:code:{scene}:{_norm(email)}"


def _attempt_key(scene: str, email: str) -> str:
    return f"email_code:try:{scene}:{_norm(email)}"


def _cooldown_key(email: str) -> str:
    return f"email_code:cd:{_norm(email)}"


def _quota_key(email: str) -> str:
    """按自然小时分桶计数，key 自带小时戳 → TTL 到点自动清理，不用手动重置。"""
    bucket = datetime.now().strftime("%Y%m%d%H")
    return f"email_code:quota:{_norm(email)}:{bucket}"


async def _read_int(key: str) -> int:
    raw = await get_cache().get(key)
    return int(raw) if raw and raw.isdigit() else 0


async def _raise_if_rate_limited(email: str) -> None:
    cache = get_cache()
    if await cache.get(_cooldown_key(email)):
        raise BusinessError(
            ERR_EMAIL_CODE_TOO_FREQUENT,
            f"验证码已发送，请 {settings.email_code_resend_seconds} 秒后再试",
            429,
        )
    if await _read_int(_quota_key(email)) >= settings.email_code_hourly_limit:
        raise BusinessError(
            ERR_EMAIL_CODE_TOO_FREQUENT,
            "该邮箱获取验证码过于频繁，请稍后再试",
            429,
        )


async def _mark_sent(email: str) -> None:
    """记一次发送：设重发冷却 + 累加本小时计数。"""
    cache = get_cache()
    await cache.set(_cooldown_key(email), "1", settings.email_code_resend_seconds)
    key = _quota_key(email)
    await cache.set(key, str(await _read_int(key) + 1), 3600)


async def send_code(email: str, scene: str) -> None:
    """限流校验 → 生成并暂存验证码 → 发信。

    发信失败会把刚占掉的冷却和验证码一起撤掉：否则用户什么都没收到，
    却要干等 60 秒才能重试。
    """
    await _raise_if_rate_limited(email)

    code = f"{secrets.randbelow(1_000_000):06d}"
    cache = get_cache()
    await cache.set(_code_key(scene, email), code, settings.email_code_ttl_seconds)
    await _mark_sent(email)

    scene_label = "登录" if scene == SCENE_LOGIN else "重置密码"
    minutes = max(1, settings.email_code_ttl_seconds // 60)
    sent = await notifier.notify(
        "竞品雷达：邮箱验证码",
        f"你正在{scene_label}，验证码是 {code}，{minutes} 分钟内有效。"
        "如非本人操作，请忽略本邮件，你的账号不会受到影响。",
        to=[_norm(email)],
    )
    if not sent:
        await _clear_cooldown(email)
        await cache.delete(_code_key(scene, email))
        raise BusinessError(
            ERR_EMAIL_SEND_FAILED,
            "验证码发送失败：请检查「系统设置」里的 SMTP 是否配置完整，"
            "以及 NOTIFY_ENABLED 是否已开启",
            503,
        )
    if settings.notify_backend != "smtp":
        # 开发模式（NOTIFY_BACKEND=log）：邮件没真发出去，验证码只落在后端日志里。
        # 用 warning 级别 + 打印验证码，方便本地开发时直接从控制台取。
        logger.warning(
            "【开发模式】NOTIFY_BACKEND=%s，验证码未真正发信，仅写日志：%s -> %s",
            settings.notify_backend,
            _norm(email),
            code,
        )


async def verify_code(email: str, scene: str, code: str) -> None:
    """校验验证码：不通过直接抛业务异常；通过则消费掉（一次性）。

    失败累计到 `MAX_VERIFY_ATTEMPTS` 次会作废当前验证码，逼迫重新获取，
    让「猜 6 位数字」在有效期内不可能成功。
    """
    cache = get_cache()
    key = _code_key(scene, email)
    stored = await cache.get(key)
    supplied = (code or "").strip()

    ok = bool(stored) and secrets.compare_digest(stored, supplied)
    if ok:
        await cache.delete(key)
        await cache.delete(_attempt_key(scene, email))
        return

    attempts = await _read_int(_attempt_key(scene, email)) + 1
    if stored and attempts >= MAX_VERIFY_ATTEMPTS:
        await cache.delete(key)
        await cache.delete(_attempt_key(scene, email))
        raise BusinessError(
            ERR_EMAIL_CODE_INVALID,
            "验证码错误次数过多，已失效，请重新获取",
            400,
        )
    await cache.set(
        _attempt_key(scene, email), str(attempts), settings.email_code_ttl_seconds
    )
    raise BusinessError(ERR_EMAIL_CODE_INVALID, "验证码错误或已过期，请重新获取验证码后输入", 400)


async def _clear_cooldown(email: str) -> None:
    await get_cache().delete(_cooldown_key(email))
