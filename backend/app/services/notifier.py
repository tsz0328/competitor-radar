"""通知推送（里程碑 10.2，可选）。

默认关闭（`NOTIFY_ENABLED=false`）；开启后可选两个后端：
- `log`  ：只写日志。零外部依赖，开发与验证用。
- `smtp` ：发邮件。需要配置 `SMTP_*`。

两条硬约束：
1. **推送失败绝不影响主流程**——抓取与周报生成照常完成，失败只记一条 warning；
2. 通知内容只含统计与标题，**不含抓取到的页面正文**（与日志同口径）。
"""
import asyncio
import logging
import smtplib
from email.message import EmailMessage

from app.core.config import get_settings
from app.services.system_settings import get_effective_smtp_config

logger = logging.getLogger(__name__)
settings = get_settings()


def _recipients(to: list[str] | None) -> list[str]:
    """收件人：只认调用方给的（那个用户自己的邮箱），没给就回退**显式配置的**运维邮箱。

    设计红线：任何「某个用户的事」都必须传 `to`，且收件人只能是该用户本人。
    没传 `to` 的只允许是系统级运维通知（如抓取任务整体异常），发给显式配置的
    `NOTIFY_RECIPIENTS`；**绝不再回退到 SMTP_USERNAME / SMTP_SENDER**——发件账号
    往往就是管理员本人的邮箱，一旦回退，用户的竞品动态会被静默投进管理员信箱。
    没有显式配置时，宁可返回空列表让上层落一条 warning，也不猜收件人。
    """
    if to:
        return [item.strip() for item in to if item and item.strip()]
    raw = settings.notify_recipients
    return [item.strip() for item in raw.split(",") if item.strip()]


def _send_smtp(
    title: str,
    message: str,
    recipients: list[str],
    sender: str,
    host: str,
    port: int,
    username: str,
    password: str,
) -> None:
    """同步发送邮件；由调用方丢进线程池，避免阻塞事件循环。"""
    if not recipients:
        raise RuntimeError("未配置收件人（该用户没填通知邮箱，NOTIFY_RECIPIENTS 也为空）")
    if not host:
        raise RuntimeError("未配置 SMTP 服务器（SMTP_HOST）")
    if not username or not password:
        raise RuntimeError("未配置 SMTP 用户名或授权码")

    mail = EmailMessage()
    mail["Subject"] = title
    mail["From"] = sender or username
    mail["To"] = ", ".join(recipients)
    mail.set_content(message)

    if port == 465:
        with smtplib.SMTP_SSL(host, port, timeout=15) as client:
            client.login(username, password)
            client.send_message(mail)
    else:
        with smtplib.SMTP(host, port, timeout=15) as client:
            client.starttls()
            client.login(username, password)
            client.send_message(mail)


async def notify(
    title: str,
    message: str,
    to: list[str] | None = None,
    email_enabled: bool = True,
) -> bool:
    """发送一条通知；返回是否真的发出去了（未开启或发送失败都返回 False）。

    to 指定收件人——**凡是"某个用户的事"，必须传本人的邮箱**；
    不传只适用于系统级运维通知（发给 NOTIFY_RECIPIENTS，未配置则不发）。

    email_enabled：用户级「接收邮件通知」开关（默认开启）。为 False 时直接跳过，
    不发出也不告警——这是用户的主动选择，不是配置错误。验证码等账号类邮件
    调用方不传该参数（走默认 True），不受开关影响。
    """
    if not settings.notify_enabled:
        return False
    if not email_enabled:
        return False
    # SMTP 连接参数读运行时生效值（界面可覆盖 .env 的 SMTP_*）
    cfg = await get_effective_smtp_config()
    try:
        if settings.notify_backend == "smtp":
            await asyncio.to_thread(
                _send_smtp,
                title,
                message,
                _recipients(to),
                cfg["sender"],
                cfg["host"],
                cfg["port"],
                cfg["username"],
                cfg["password"],
            )
        else:
            logger.info("notify[log] %s ｜ %s", title, message)
        return True
    except Exception as exc:  # noqa: BLE001 - 推送是旁路，绝不能打断主流程
        logger.warning(
            "通知发送失败（%s）：%s: %s",
            settings.notify_backend,
            type(exc).__name__,
            str(exc)[:120],
        )
        return False


async def send_test_email(cfg: dict, to: str) -> None:
    """管理端「发送测试邮件」：用运行时生效配置给指定收件人发一封测试信。

    与 notify 不同：这是管理员主动验证配置，不受 NOTIFY_ENABLED 总开关限制；
    配置缺失（没填 host / 用户名 / 授权码）时 _send_smtp 会抛 RuntimeError，
    由调用方（api/admin.py）捕获后把失败原因带给前端。
    """
    await asyncio.to_thread(
        _send_smtp,
        "【竞品雷达】SMTP 测试邮件",
        "这是一封测试邮件：如果你收到它，说明发件配置（服务器 / 端口 / "
        "用户名 / 授权码 / 发件邮箱）工作正常。",
        [to],
        cfg["sender"],
        cfg["host"],
        cfg["port"],
        cfg["username"],
        cfg["password"],
    )
