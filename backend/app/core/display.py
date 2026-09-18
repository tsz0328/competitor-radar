"""展示层小工具：域名清理与首字母头像配色（事件、周报等多处共用）。"""
import re

_SCHEME_RE = re.compile(r"^https?://", re.I)
_WWW_RE = re.compile(r"^www\.", re.I)

# 固定的一组柔和配色，按名称哈希取用，保证同一竞品颜色稳定
ICON_TONES: tuple[tuple[str, str], ...] = (
    ("#e6f7f0", "#10a37f"),
    ("#e8f0fe", "#4285f4"),
    ("#f5e8df", "#c96442"),
    ("#e6faff", "#13c2c2"),
    ("#f0e9ff", "#6b32d9"),
    ("#fff3e6", "#fa8c16"),
)


def clean_host(url: str | None) -> str:
    """https://www.notion.so/x → notion.so"""
    host = _SCHEME_RE.sub("", url or "").split("/")[0].strip()
    return _WWW_RE.sub("", host)


def icon_tone(key: str) -> tuple[str, str]:
    """按名称取一组 (背景色, 前景色)。"""
    total = sum(ord(ch) for ch in (key or "?"))
    return ICON_TONES[total % len(ICON_TONES)]


def icon_text(name: str) -> str:
    """首字母头像文字。"""
    return (name or "?").strip()[:1].upper() or "?"
