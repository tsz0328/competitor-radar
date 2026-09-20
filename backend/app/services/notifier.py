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


def _recipients(to: list[str] | None, fallback_sender: str) -> list[str]:
    """收件人：优先调用方给的（某用户自己的通知邮箱），否则回退运维配置。

    - 传了 to：这是"某个用户的事"（如他的竞品出现高优变化），只发给他自己；
    - 没传：系统级通知（如周报批次完成），发给 NOTIFY_RECIPIENTS / SMTP_USERNAME /
      SMTP_SENDER（fallback_sender 为运行时生效的发件人）。
    """
    if to:
        return [item.strip() for item in to if item and item.strip()]
    raw = settings.notify_recipients or settings.smtp_username or fallback_sender
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


async def notify(title: str, message: str, to: list[str] | None = None) -> bool:
    """发送一条通知；返回是否真的发出去了（未开启或发送失败都返回 False）。

    to 指定收件人（用户自己的通知邮箱）；不传则回退运维配置的收件人。
    """
    if not settings.notify_enabled:
        return False
    # SMTP 连接参数读运行时生效值（界面可覆盖 .env 的 SMTP_*）
    cfg = await get_effective_smtp_config()
    try:
        if settings.notify_backend == "smtp":
            await asyncio.to_thread(
                _send_smtp,
                title,
                message,
                _recipients(to, cfg["sender"]),
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
