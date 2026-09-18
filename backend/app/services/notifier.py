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

logger = logging.getLogger(__name__)
settings = get_settings()


def _recipients() -> list[str]:
    """收件人：优先 NOTIFY_RECIPIENTS，留空则发给自己（SMTP_USERNAME）。"""
    raw = settings.notify_recipients or settings.smtp_username or settings.smtp_sender
    return [item.strip() for item in raw.split(",") if item.strip()]


def _send_smtp(title: str, message: str) -> None:
    """同步发送邮件；由调用方丢进线程池，避免阻塞事件循环。"""
    recipients = _recipients()
    if not recipients:
        raise RuntimeError("未配置收件人（NOTIFY_RECIPIENTS 或 SMTP_USERNAME）")
    if not settings.smtp_host:
        raise RuntimeError("未配置 SMTP_HOST")

    mail = EmailMessage()
    mail["Subject"] = title
    mail["From"] = settings.smtp_sender or settings.smtp_username
    mail["To"] = ", ".join(recipients)
    mail.set_content(message)

    if settings.smtp_port == 465:
        with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=15) as client:
            client.login(settings.smtp_username, settings.smtp_password)
            client.send_message(mail)
    else:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as client:
            client.starttls()
            client.login(settings.smtp_username, settings.smtp_password)
            client.send_message(mail)


async def notify(title: str, message: str) -> bool:
    """发送一条通知；返回是否真的发出去了（未开启或发送失败都返回 False）。"""
    if not settings.notify_enabled:
        return False
    try:
        if settings.notify_backend == "smtp":
            await asyncio.to_thread(_send_smtp, title, message)
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
