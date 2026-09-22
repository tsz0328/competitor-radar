"""生成一个最小复现页：复刻 CompetitorFormDialog 里 URL 输入框尾部图标的真实 DOM，
渲染「改动前 / 改动后」两版，供截图对比。用完可删。"""
import re
from pathlib import Path

ROOT = Path(r"D:/project/competitor-radar")
EP_CSS = (ROOT / "frontend/node_modules/element-plus/dist/index.css").read_text(encoding="utf-8")
APP_CSS = (ROOT / "frontend/src/styles/global.css").read_text(encoding="utf-8")
ICONS = (ROOT / "frontend/node_modules/@element-plus/icons-vue/dist/index.js").read_text(encoding="utf-8")


def icon_path(name: str) -> str:
    i = ICONS.find(f'name: "{name}"')
    if i < 0:
        raise SystemExit(f"icon {name} not found")
    seg = ICONS[i:i + 4000]
    m = re.search(r'd:\s*"([^"]+)"', seg)
    if not m:
        raise SystemExit(f"path for {name} not found")
    return m.group(1)


def svg(name: str, cls: str = "", style: str = "", title: str = "") -> str:
    d = icon_path(name)
    t = f' title="{title}"' if title else ""
    return (
        f'<span class="el-icon {cls}" style="{style}"{t}>'
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024">'
        f'<path fill="currentColor" d="{d}"></path></svg></span>'
    )


def url_input(value: str, prefix: str = "") -> str:
    """复刻 el-input（含 suffix：状态图标 + 打开链接图标）"""
    check = svg("Check", style="color:var(--el-color-success)")
    link = svg("Link", cls="url-link active", title="打开该网址")
    pre = f'<span class="el-input__prefix">{prefix}</span>' if prefix else ""
    return (
        '<div class="el-input source-url">'
        '<div class="el-input__wrapper" tabindex="-1">'
        + pre
        + f'<input class="el-input__inner" type="text" value="{value}" readonly>'
        '<span class="el-input__suffix"><span class="el-input__suffix-inner">'
        + check + link
        + "</span></span></div></div>"
    )


def rows(variant: str) -> str:
    prefix = svg("Link", style="color:var(--app-text-color-placeholder)")
    pairs = [
        ("官网地址", "https://www.tongyi.cn", prefix),
        ("应用商店页", "https://www.tongyi.cn", ""),
        ("服务状态页", "https://www.qianwen.com/health", ""),
    ]
    out = []
    for label, url, pre in pairs:
        out.append(
            f'<div class="source-row"><span class="source-name">{label}</span>'
            f'{url_input(url, pre)}</div>'
        )
    return f'<div class="variant {variant}">' + "".join(out) + "</div>"


HTML = f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>suffix icons</title>
<style>{EP_CSS}</style>
<style>{APP_CSS}</style>
<style>
  body {{ margin: 0; background: #fff; }}
  .panel {{ width: min(980px, 96vw); margin: 0 auto; padding: 18px 0 8px; }}
  .source-row {{ display: flex; align-items: center; gap: 1vw; margin-bottom: 1.6vh; }}
  .source-name {{
    width: 6.5em; flex-shrink: 0; box-sizing: border-box;
    font-size: 0.88vmax; color: var(--app-text-color-regular);
  }}
  .source-url {{ flex: 1; min-width: 0; }}
  .url-link {{ cursor: pointer; color: var(--app-text-color-placeholder); }}
  .url-link.active {{ color: var(--el-color-primary); }}
  .caption {{ font-size: 0.8vmax; color: #909399; margin: 0 0 0.8vh; }}
  /* ↓↓↓ 本次新增的规则（只作用于 .after，用于对比） ↓↓↓ */
  .after .el-input__suffix-inner {{ gap: 0.45em; font-size: 1.3em; }}
</style></head>
<body>
<div class="panel">
  <div class="caption">BEFORE — 改动前（继承 1em，两图标紧贴）</div>
  {rows("before")}
  <div class="caption" style="margin-top:2.4vh">AFTER — 改动后（1.3em + 0.45em 间距）</div>
  {rows("after")}
</div>
</body></html>
"""

out = Path(__file__).with_name("suffix-icon.html")
out.write_text(HTML, encoding="utf-8")
print("written", out, len(HTML))
