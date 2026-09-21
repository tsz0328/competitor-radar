"""为管理员账号生成模拟竞品监测数据，方便前后端联调测试。

数据范围（只改业务数据，不碰用户本身 / LLM 密钥）：
- competitors / monitor_sources / page_snapshots / intelligence_events
- event_reads（把部分高优事件标为已读）
- trend_insights（每个竞品一条趋势）
- crawl_logs（手动 + 定时 的成功/失败/跳过日志）
- weekly_reports（复用真实生成服务，额外产出「上一周周报」+「本月月报」，
  不覆盖已有的当前周报告，便于顺带测试「重复周期」的处理）

幂等说明：本脚本是「追加式」造数，重复运行会再插一批。若需从零重置，
请先跑 `.codebuddy/reset_accounts.py apply <邮箱> <密码>` 清空后再 seed。

用法（在 backend 目录或任意目录运行均可，脚本内部会定位库文件）：
    python .codebuddy/seed_mock_data.py
"""
import asyncio
import os
import shutil
import sqlite3
import sys
import urllib.request
import uuid
from datetime import date, datetime, timedelta

BASE = r"D:\project\competitor-radar\backend"
DB = os.path.join(BASE, "dev.db")

# 参照基准：以「今天」动态计算自然周/自然月，保证模拟数据始终落在当前窗口内
TODAY = date.today()
MONDAY = TODAY - timedelta(days=TODAY.weekday())


def dt(d: date, hour: int = 9, minute: int = 0) -> str:
    """把本地时刻转成 UTC（Asia/Shanghai = +8）后存库，与应用的时区口径一致。"""
    return (datetime(d.year, d.month, d.day, hour, minute) - timedelta(hours=8)).strftime(
        "%Y-%m-%d %H:%M:%S"
    )


def last_week(d: date) -> date:
    """返回 d 所在周的周一。"""
    return d - timedelta(days=d.weekday())


# ---- 竞品与监控源模板（源类型 / 名称 / 地址 / 是否启用 / 健康度）----
# 跨品类代表竞品：让不同行业的用户一看就懂「我也能这样用」，
# 每个竞品都配 homepage（必有）+ 定价页/更新日志/帮助文档等可抓源，保证有监控价值。
COMPETITORS = [
    {
        "name": "飞书",
        "category": "协作办公",
        "url": "https://www.feishu.cn",
        "logo": "https://www.feishu.cn/favicon.ico",
        "sources": [
            ("homepage", "官网首页", "https://www.feishu.cn/"),
            ("changelog", "更新日志", "https://www.feishu.cn/whats-new"),
            ("pricing", "定价页", "https://www.feishu.cn/pricing"),
            ("status", "服务状态页", "https://status.feishu.cn"),
        ],
    },
    {
        "name": "钉钉",
        "category": "协作办公",
        "url": "https://www.dingtalk.com",
        "logo": "https://gw.alicdn.com/imgextra/i3/O1CN014ZbI6ZTEhdC0ttN2_!!6000000003783-2-tps-444-444.png",
        "sources": [
            ("homepage", "官网首页", "https://www.dingtalk.com"),
            ("changelog", "更新日志", "https://www.dingtalk.com/changelog"),
            ("pricing", "定价页", "https://www.dingtalk.com/pricing"),
        ],
    },
    {
        "name": "企业微信",
        "category": "协作办公",
        "url": "https://work.weixin.qq.com",
        "logo": "https://wwcdn.weixin.qq.com/node/wwnl/wwnl/style/images/independent/favicon/favicon_48h$c976bd14.png",
        "sources": [
            ("homepage", "官网首页", "https://work.weixin.qq.com"),
            ("changelog", "更新日志", "https://work.weixin.qq.com/updates"),
            ("docs", "帮助文档", "https://work.weixin.qq.com/help"),
        ],
    },
    {
        "name": "腾讯会议",
        "category": "在线会议",
        "url": "https://meeting.tencent.com",
        "logo": "https://cdn.meeting.tencent.com/assets/next-website/logo128.png",
        "sources": [
            ("homepage", "官网首页", "https://meeting.tencent.com"),
            ("pricing", "定价页", "https://meeting.tencent.com/price"),
            ("changelog", "更新日志", "https://meeting.tencent.com/updates"),
        ],
    },
    {
        "name": "Notion",
        "category": "文档协作",
        "url": "https://www.notion.so",
        "logo": "https://www.notion.com/front-static/logo-ios.png",
        "sources": [
            ("homepage", "官网首页", "https://www.notion.so"),
            ("pricing", "定价页", "https://www.notion.so/pricing"),
            ("rss", "RSS 订阅", "https://www.notion.so/feed"),
        ],
    },
    {
        "name": "Asana",
        "category": "项目管理",
        "url": "https://asana.com",
        "logo": "https://asana.com/favicon.ico",
        "sources": [
            ("homepage", "官网首页", "https://asana.com"),
            ("pricing", "定价页", "https://asana.com/pricing"),
        ],
    },
    {
        "name": "Figma",
        "category": "设计工具",
        "url": "https://www.figma.com",
        "logo": "https://static.figma.com/app/icon/2/touch-180.png",
        "sources": [
            ("homepage", "官网首页", "https://www.figma.com"),
            ("pricing", "定价页", "https://www.figma.com/pricing"),
            ("changelog", "更新日志", "https://www.figma.com/whats-new"),
        ],
    },
    {
        "name": "GitHub",
        "category": "开发者工具",
        "url": "https://github.com",
        "logo": "https://github.com/fluidicon.png",
        "sources": [
            ("homepage", "官网首页", "https://github.com"),
            ("pricing", "定价页", "https://github.com/pricing"),
            ("changelog", "更新日志", "https://github.blog/changelog"),
        ],
    },
    {
        "name": "Keep",
        "category": "运动健身",
        "url": "https://www.gotokeep.com",
        "logo": "https://www.gotokeep.com/icons/favicon.ico",
        "sources": [
            ("homepage", "官网首页", "https://www.gotokeep.com"),
            ("blog", "官方博客", "https://www.gotokeep.com/blog"),
        ],
    },
]


def main():
    sys.path.insert(0, BASE)

    # 先备份，再写库
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    bak = f"{DB}.bak-{stamp}-before-mock"
    shutil.copy2(DB, bak)
    print("备份 ->", bak)

    conn = sqlite3.connect(DB)
    try:
        seed(conn)
    finally:
        conn.close()

    # 复用真实周报服务生成报告（在 backend 目录下运行，ORM 才能连到 dev.db）
    os.chdir(BASE)
    asyncio.run(generate_reports())


def seed(conn):
    # 目标账号：取第一个管理员；找不到就中止
    admin = conn.execute(
        "select id from users where is_admin=1 order by id limit 1"
    ).fetchone()
    if not admin:
        print("!! 未找到管理员账号，中止。先创建管理员再跑本脚本。")
        sys.exit(1)
    uid = admin[0]
    print(f"目标账号 id={uid}")

    # 清空本次要造的数据（避免重复运行叠加出糖尿病级别的数据量）
    for t in [
        "crawl_logs",
        "trend_insights",
        "event_reads",
        "intelligence_events",
        "page_snapshots",
        "monitor_sources",
        "competitors",
    ]:
        conn.execute(f"delete from {t}")
    print("已清空本次涉及的 7 张业务表")

    # ---- 竞品 + 监控源 ----
    competitor_ids = {}
    source_ids = {}
    for cp in COMPETITORS:
        cur = conn.execute(
            "insert into competitors (user_id, name, official_url, category, logo_url, status) "
            "values (?,?,?,?,?,'active')",
            (uid, cp["name"], cp["url"], cp["category"], cp.get("logo", "")),
        )
        cid = cur.lastrowid
        competitor_ids[cp["name"]] = cid
        for stype, sname, surl in cp["sources"]:
            render = "browser" if stype in ("homepage", "pricing", "changelog", "docs", "status", "app_store") else "http"
            interval = 1440 if stype in (
                "homepage", "pricing", "changelog", "app_store"
            ) else (10080 if stype == "docs" else 60)
            cur = conn.execute(
                "insert into monitor_sources "
                "(competitor_id, source_type, name, url, render_mode, interval_minutes, "
                " enabled, last_crawled_at, last_status, fail_count) "
                "values (?,?,?,?,?,?,1,?,?,0)",
                (cid, stype, sname, surl, render, interval, dt(TODAY, 6), "success"),
            )
            source_ids[(cp["name"], stype)] = cur.lastrowid
    print(f"竞品 {len(COMPETITORS)} 个，监控源 {conn.total_changes} 新增")

    # ---- 页面临拍 ----
    # (竞品, 源类型, 日期, 是否成功, 是否变化, http, 失败原因)
    snap_rows = [
        ("飞书", "homepage", 16, 1, 1, 200, None),
        ("飞书", "changelog", 17, 1, 1, 200, None),
        ("飞书", "pricing", 15, 1, 0, 200, None),
        ("飞书", "status", 18, 0, 0, 503, "上游 5xx：服务中断"),
        ("钉钉", "homepage", 14, 1, 0, 200, None),
        ("钉钉", "changelog", 18, 1, 1, 200, None),
        ("企业微信", "homepage", 17, 1, 1, 200, None),
        ("腾讯会议", "pricing", 16, 1, 0, 200, None),
        ("腾讯会议", "changelog", 19, 1, 1, 200, None),
        ("Notion", "homepage", 15, 1, 1, 200, None),
        ("Notion", "pricing", 18, 0, 0, 429, "限流"),
        ("Notion", "rss", 19, 1, 0, 200, None),
        ("Asana", "homepage", 15, 1, 1, 200, None),
        ("Asana", "pricing", 16, 1, 0, 200, None),
        ("Figma", "homepage", 17, 1, 1, 200, None),
        ("Figma", "changelog", 18, 1, 1, 200, None),
        ("GitHub", "homepage", 16, 1, 1, 200, None),
        ("GitHub", "pricing", 19, 1, 0, 200, None),
    ]
    for name, stype, day, ok, changed, http, reason in snap_rows:
        sid = source_ids[(name, stype)]
        cid = competitor_ids[name]
        url = dict((c["name"], c) for c in COMPETITORS)[name]
        surl = next(s[2] for s in url["sources"] if s[0] == stype)
        conn.execute(
            "insert into page_snapshots "
            "(competitor_id, source_id, source_type, url, clean_text, content_hash, "
            " http_status, is_success, fail_reason, change_detected, diff_text, crawled_at) "
            "values (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                cid, sid, stype, surl,
                f"{name}-{sname_of(stype)} 抓取到的模拟正文",
                f"hash{cid}{sid}{day}",
                http, ok, reason, changed,
                "新增了几行明显变化" if changed else None,
                dt(TODAY.replace(day=day) if day else TODAY, 8),
            ),
        )
    print("页面临拍", len(snap_rows), "条")

    # ---- 情报事件 ----
    # (竞品, 源类型, 类型, 优先级, 相对今天天数, 标题, 摘要)
    ev_rows = [
        # 本周（1~7 天前）：各类竞品的最新动态
        ("飞书", "changelog", "new_feature", "high", 2, "飞书发布多维表格 AI 智能助手",
         "多维表格接入 AI，可自动拆解表格结构、生成公式"),
        ("飞书", "pricing", "price_change", "mid", 5, "飞书调整标准版套餐容量权益",
         "标准版席位容量有所上调"),
        ("钉钉", "changelog", "new_feature", "mid", 1, "钉钉上线 AI 一键会议纪要",
         "会议结束即可生成结构化纪要并自动分发"),
        ("钉钉", "pricing", "price_change", "high", 4, "钉钉下调基础版团队人数限制",
         "基础版团队规模上限收紧"),
        ("企业微信", "homepage", "new_feature", "high", 3, "企业微信打通视频号直播带货",
         "企微会话内可接入视频号直播商品"),
        ("企业微信", "docs", "public_sentiment", "mid", 1, "出现服务可用性相关反馈",
         "个别地区连接不稳定，官方暂无说明"),
        ("腾讯会议", "changelog", "new_feature", "high", 3, "腾讯会议上线 AI 实时字幕翻译",
         "会议中实时转写并支持多语言互译"),
        ("腾讯会议", "pricing", "price_change", "mid", 7, "腾讯会议调整个人版收费策略",
         "个人版新购价格小幅上调"),
        ("Notion", "homepage", "new_feature", "high", 2, "Notion 发布全新 AI 工作区",
         "整合知识库与自动化工作流"),
        ("Notion", "pricing", "price_change", "mid", 4, "Notion 调整商业版席位定价",
         "单席位价格上调"),
        ("Notion", "rss", "content_update", "mid", 1, "官方博客更新 AI 模板合集",
         "发布多套面向团队的 AI 模板"),
        ("Asana", "homepage", "new_feature", "mid", 2, "Asana 上线 AI 项目规划助手",
         "自动拆分任务并生成排期建议"),
        ("Figma", "changelog", "new_feature", "high", 1, "Figma 发布 AI 设计生成",
         "输入描述即可生成可编辑界面"),
        ("GitHub", "changelog", "new_feature", "mid", 2, "GitHub Copilot 新版本发布",
         "代码补全与审查能力全面增强"),
        # 上一周期（用于让「上一周周报」有内容）
        ("飞书", "changelog", "new_feature", "mid", 9, "飞书优化移动端协同体验",
         "移动端编辑冲突显著降低"),
        ("钉钉", "homepage", "content_update", "low", 10, "钉钉品牌官网改版",
         "首页视觉与文案整体刷新"),
        ("企业微信", "changelog", "content_update", "low", 11, "客户群管理规则更新",
         "群发限制有所调整"),
        ("腾讯会议", "homepage", "other", "low", 12, "腾讯会议品牌升级",
         "发布全新 VI 体系"),
        ("Notion", "rss", "content_update", "low", 9, "Notion 教育优惠延长",
         "教育邮箱折扣续期"),
        ("Asana", "pricing", "price_change", "low", 12, "Asana 调整免费版额度",
         "免费协作席位数量收紧"),
        ("Figma", "homepage", "content_update", "low", 11, "Figma 官网改版",
         "导航与定价页布局更新"),
        ("GitHub", "homepage", "content_update", "low", 10, "GitHub 首页更新",
         "首页推荐位与文案刷新"),
        # 月初（15~19 天前），填满本月月报的曲线
        ("飞书", "status", "public_sentiment", "mid", 19, "服务状态页出现波动",
         "个别时段访问延迟上升"),
        ("钉钉", "changelog", "new_feature", "high", 17, "钉钉上线审批自动化机器人",
         "低代码审批流程可自我驱动"),
        ("腾讯会议", "changelog", "new_feature", "mid", 16, "腾讯会议优化录屏功能",
         "录屏清晰度与存储时长提升"),
        ("Notion", "homepage", "public_sentiment", "mid", 15, "Notion 社区讨论升温",
         "海外社区对定价调整讨论增多"),
        ("GitHub", "pricing", "content_update", "low", 18, "GitHub 免费额度说明更新",
         "文档补充免费档使用限制"),
    ]
    event_ids = []
    for name, stype, etype, prio, days_ago, title, summ in ev_rows:
        cid = competitor_ids[name]
        sid = source_ids.get((name, stype))
        created = dt(TODAY - timedelta(days=days_ago), 9)
        # 让部分事件带不同的置信度，便于排序/高影响区分
        conf = 0.55 if prio == "low" else (0.8 if prio == "high" else 0.68)
        cur = conn.execute(
            "insert into intelligence_events "
            "(competitor_id, source_id, event_type, title, summary, ai_analysis, "
            " keywords, confidence, priority, created_at) values (?,?,?,?,?,?,?,?,?,?)",
            (
                cid, sid, etype, title, summ,
                "推测对方产品与运营节奏在加快，建议跟进。" if prio == "high" else "影响暂不明确，建议持续观察。",
                '["模拟"]', conf, prio, created,
            ),
        )
        event_ids.append(cur.lastrowid)
    print("情报事件", len(ev_rows), "条")

    # ---- 已读：把部分高优事件标为已读，其余留未读 ----
    read_count = 0
    for i, eid in enumerate(event_ids):
        if i % 3 != 0:  # 三分之二标已读，留一些未读测未读角标
            conn.execute(
                "insert into event_reads (user_id, event_id, is_read, read_at) "
                "values (?,?,1,?)",
                (uid, eid, dt(TODAY, 10)),
            )
            read_count += 1
    print("已读记录", read_count, "条")

    # ---- 趋势 ----
    trends = [
        ("飞书", "rising", "活跃度上升", "近 30 天功能迭代与定价调整并存。",
         ["多维表格 AI 上线", "套餐权益调整"], 6, 1),
        ("钉钉", "rising", "活跃度上升", "AI 能力集中释放，商业化调整频繁。",
         ["AI 会议纪要", "基础版限制收紧"], 4, 1),
        ("企业微信", "stable", "节奏平稳", "以功能打通为主，未见激烈动作。",
         ["视频号直播带货"], 2, 0),
        ("腾讯会议", "rising", "活跃度上升", "功能与价格双线推进。",
         ["AI 字幕翻译", "个人版调价"], 3, 1),
        ("Notion", "stable", "节奏平稳", "AI 与定价更新为主，舆论有波动。",
         ["AI 工作区", "商业版调价"], 4, 0),
        ("Asana", "stable", "节奏平稳", "聚焦 AI 项目能力，节奏温和。",
         ["AI 项目规划助手"], 2, 0),
        ("Figma", "rising", "活跃度上升", "AI 设计能力集中上线。",
         ["AI 设计生成"], 2, 1),
        ("GitHub", "rising", "活跃度上升", "Copilot 持续迭代，生态活跃。",
         ["Copilot 新版本", "免费额度说明"], 3, 1),
    ]
    for name, direction, d_label, summ, highs, ecnt, hi in trends:
        conn.execute(
            "insert into trend_insights "
            "(competitor_id, period_days, direction, summary, highlights, "
            " event_count, high_impact_count, coverage_days) values (?,?,?,?,?,?,?,?)",
            (competitor_ids[name], 30, direction, summ, str(highs), ecnt, hi, 28),
        )
    print("趋势", len(trends), "条")

    # ---- 抓取日志 ----
    logs = [
        ("飞书", "changelog", "scheduler", "success", 200, 1, 0, 0, 920, None),
        ("飞书", "status", "scheduler", "failed", 503, 0, 0, 0, 1840, "上游 5xx"),
        ("飞书", "pricing", "scheduler", "success", 200, 0, 0, 0, 690, None),
        ("钉钉", "pricing", "manual", "success", 200, 0, 0, 0, 760, None),
        ("钉钉", "changelog", "scheduler", "success", 200, 1, 0, 1, 810, None),
        ("企业微信", "homepage", "manual", "success", 200, 1, 0, 1, 1300, None),
        ("企业微信", "docs", "scheduler", "skipped", None, 0, 0, 0, 0, "未到调度时间"),
        ("腾讯会议", "changelog", "scheduler", "success", 200, 1, 0, 1, 640, None),
        ("腾讯会议", "pricing", "scheduler", "success", 200, 0, 0, 0, 480, None),
        ("Notion", "homepage", "manual", "success", 200, 1, 0, 1, 1500, None),
        ("Notion", "pricing", "scheduler", "failed", 429, 0, 0, 0, 2100, "限流"),
        ("Notion", "rss", "scheduler", "success", 200, 0, 1, 0, 320, None),
        ("Asana", "homepage", "scheduler", "success", 200, 1, 0, 1, 880, None),
        ("Asana", "pricing", "manual", "success", 200, 0, 0, 0, 520, None),
        ("Figma", "changelog", "scheduler", "success", 200, 1, 0, 1, 940, None),
        ("Figma", "homepage", "manual", "success", 200, 0, 0, 0, 610, None),
        ("GitHub", "changelog", "scheduler", "success", 200, 1, 0, 1, 870, None),
        ("GitHub", "pricing", "manual", "success", 200, 0, 0, 0, 540, None),
    ]
    for idx, (name, stype, trigger, status, http, changed, first, ev, dur, err) in enumerate(logs):
        cp = next(c for c in COMPETITORS if c["name"] == name)
        url = next(s[2] for s in cp["sources"] if s[0] == stype)
        sname = next(s[1] for s in cp["sources"] if s[0] == stype)
        conn.execute(
            "insert into crawl_logs "
            "(user_id, competitor_id, competitor_name, source_id, source_name, source_type, "
            " url, trigger, status, http_status, changed, first_time, event_created, "
            " duration_ms, error, created_at) values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (uid, competitor_ids[name], name, source_ids.get((name, stype)), sname, stype,
             url, trigger, status, http, changed, first, ev, dur, err, dt(TODAY, 7 - min(idx, 5))),
        )
    print("抓取日志", len(logs), "条")

    # ---- 图标库：托管官网图标，竞品 logo 指向 /api/icons/... ----
    seed_icons(conn)

    conn.commit()
    print("=== seed 完成 ===")


def sname_of(stype: str) -> str:
    return next(s[1] for c in COMPETITORS for s in c["sources"] if s[0] == stype)


# ---- 图标库：把官网图标托管到后端，演示「优先命中后端图标库」的解析链路 ----
# 与后端 icon_library 的口径保持一致：白名单格式（png/jpeg/webp/gif），
# 域名规范化 = 小写 + 去 www。下载失败（403/返回 HTML 等）就跳过——
# 那些站点正好留给管理员在「全部竞品」页手动上传，形成完整演示闭环。
ICON_EXT = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
    "image/gif": ".gif",
}


def _norm_host(url: str) -> str:
    """与后端 services/icon_library.normalize_host 同口径的小写去 www 主机名。"""
    text = (url or "").strip()
    if not text:
        return ""
    if "://" in text:
        text = text.split("://", 1)[1]
    host = text.split("/")[0].split("?")[0].split("#")[0].strip().lower()
    return host[4:] if host.startswith("www.") else host


def _download_icon(url: str) -> tuple[bytes, str] | None:
    """下载图标并确认返回体是白名单内图片（防把 HTML 错误页当图标存下来）。"""
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        )
        with urllib.request.urlopen(req, timeout=12) as resp:
            data = resp.read()
            ctype = (resp.headers.get("Content-Type", "") or "").split(";")[0].strip().lower()
            if not data or ctype not in ICON_EXT:
                return None
            return data, ctype
    except Exception:
        return None


def seed_icons(conn) -> None:
    """调用时机：seed() 建完竞品之后。幂等：重复运行先清库表与旧文件再重建。"""
    has_table = conn.execute(
        "select count(*) from sqlite_master where type='table' and name='icon_libraries'"
    ).fetchone()[0]
    if not has_table:
        print("!! icon_libraries 表不存在（先 alembic upgrade head 或启动一次后端），跳过图标库造数。")
        return

    icons_dir = os.path.join(BASE, "storage", "icons")
    os.makedirs(icons_dir, exist_ok=True)

    # 清掉上一轮的图标记录与落盘文件，避免重复运行积累垃圾
    for row in conn.execute("select file_name from icon_libraries").fetchall():
        path = os.path.join(icons_dir, row[0])
        if os.path.isfile(path):
            os.remove(path)
    conn.execute("delete from icon_libraries")

    by_domain: dict[str, list[int]] = {}
    for cid, url in conn.execute("select id, official_url from competitors").fetchall():
        host = _norm_host(url)
        if host:
            by_domain.setdefault(host, []).append(cid)

    count = 0
    seeded: set[str] = set()
    for cp in COMPETITORS:
        domain = _norm_host(cp["url"])
        if not domain or domain in seeded:
            continue
        seeded.add(domain)
        got = _download_icon(cp["logo"])
        if got is None:
            print(f"图标下载失败（可稍后在管理员端手动上传）：{cp['name']} {cp['logo']}")
            continue
        data, ctype = got
        file_name = uuid.uuid4().hex + ICON_EXT[ctype]
        with open(os.path.join(icons_dir, file_name), "wb") as fh:
            fh.write(data)
        conn.execute(
            "insert into icon_libraries "
            "(domain, file_name, content_type, size, uploaded_by, created_at, updated_at) "
            "values (?,?,?,?,NULL,?,?)",
            (domain, file_name, ctype, len(data), dt(TODAY, 6), dt(TODAY, 6)),
        )
        # 同域名竞品的 logo 一律指向后端托管地址（域名级事实源）
        for cid in by_domain.get(domain, []):
            conn.execute(
                "update competitors set logo_url=? where id=?",
                (f"/api/icons/{file_name}", cid),
            )
        count += 1
    print(f"图标库 {count} 条，图标托管于 storage/icons")


_report_label = {"weekly": "周报", "monthly": "月报"}


async def generate_reports():
    """复用真实报告生成服务，产出「上一周周报」 + 「本月月报」。"""
    import sqlalchemy as sa
    from app.core.database import SessionLocal, init_db
    from app.models.user import User
    from app.models.weekly_report import ReportType, WeeklyReport
    from app.services.report import generate_report

    await init_db()
    async with SessionLocal() as db:
        u = (
            await db.execute(
                sa.select(User).where(User.is_admin == 1).order_by(User.id).limit(1)
            )
        ).scalar_one_or_none()
        if u is None:
            print("!! 未找到管理员，跳过生成报告。")
            return

        for rt, weeks_ago in ((ReportType.WEEKLY, 1), (ReportType.MONTHLY, 0)):
            # 先清掉同周期的既有报告，保证脚本可重复跑（不影响已有的当前周报）
            start = (
                last_week(TODAY) - timedelta(days=7)
                if rt == ReportType.WEEKLY
                else TODAY.replace(day=1)
            )
            await db.execute(
                sa.delete(WeeklyReport).where(
                    WeeklyReport.user_id == u.id,
                    WeeklyReport.report_type == rt,
                    WeeklyReport.range_start == start,
                )
            )
            await db.flush()
            report = await generate_report(db, u, report_type=rt, weeks_ago=weeks_ago)
            await db.commit()
            print(
                f"生成{_report_label[rt.value]}：range={report.range_start}~{report.range_end} "
                f"标题={report.title}"
            )


if __name__ == "__main__":
    main()