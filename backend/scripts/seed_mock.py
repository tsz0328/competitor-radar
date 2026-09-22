"""为指定用户种入一套覆盖全部场景的竞品监控模拟数据（iso = 用户隔离）。

运行方式（在 backend 目录下）：
    .\\scripts\\seed_mock.py [username_or_id]     默认 3916408482

覆盖场景：
- 竞品：active / paused / 软删除（回收站）三种状态
- 监控源：全部 9 类 source_type（官网/定价/更新日志/博客/文档/状态页/RSS/应用商店/自定义）
- 抓取日志：success / failed(404/5xx/超时) / skipped，手动 + 定时，有无变化、是否首发、是否产出事件
- 情报事件：全部 5 类 event_type × 高/中/低优先级
- 趋势判断：rising / stable / declining 三方向
- 报告：周报 + 月报，收藏 / 免登录分享 / 软删除（回收站）
- 通知：给高优事件写未读标记（通知中心会显示未读数）

每次运行会先清空该用户此前的模拟数据再重种（模拟数据可整体丢弃，故用 replace 而非 append）。
使用项目的异步 ORM，枚举/JSON 列都走模型默认值，与正常写入一致。
"""
from __future__ import annotations

import asyncio
import secrets
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# 便于用 `python scripts/seed_mock.py` 直接从仓库任意目录运行
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import delete, select

from app.core.database import SessionLocal
from app.models import (
    Competitor,
    CrawlLog,
    EventRead,
    IntelligenceEvent,
    MonitorSource,
    PageSnapshot,
    TrendInsight,
    User,
    WeeklyReport,
)
from app.models.crawl_log import (
    STATUS_FAILED,
    STATUS_SKIPPED,
    STATUS_SUCCESS,
    TRIGGER_MANUAL,
    TRIGGER_SCHEDULER,
)
from app.models.trend import TrendDirection

TZ = timezone.utc

# 事件类型 -> 中文标签 + 标签 class（与前端 Event.vue 一致）
TYPE_META = {
    "new_feature": ("功能更新", "tag-new"),
    "price_change": ("价格变化", "tag-price"),
    "content_update": ("内容更新", "tag-update"),
    "public_sentiment": ("舆论动态", "tag-negative"),
    "other": ("其他", "tag-other"),
}
PRIORITY_LABEL = {"high": "高影响", "mid": "中影响", "low": "低影响"}


def dt(days_ago: int, hour: int = 9, minute: int = 0) -> datetime:
    """生成 relative 到现在的 UTC 时间（落库时显示按业务时区）。"""
    base = datetime.now(TZ) - timedelta(days=days_ago)
    return base.replace(hour=hour, minute=minute, second=minute % 60, microsecond=0)


# ---------------------------------------------------------------------------
# 竞品规划：覆盖 active / paused / 软删除，以及全部 9 类监控源
# sources 每项 = (source_type, 展示名, url)；render/interval 从 source_registry 派生
# ---------------------------------------------------------------------------
PLAN: dict[str, dict] = {
    "Notion": {
        "category": "协作办公", "url": "https://notion.com",
        "logo": "https://notion.com/icon.png", "status": "active",
        "sources": [
            ("homepage", "官网首页", "https://www.notion.com"),
            ("changelog", "更新日志", "https://www.notion.com/changelog"),
            ("pricing", "定价页", "https://www.notion.com/pricing"),
            ("app_store", "应用商店页", "https://apps.apple.com/app/id832036938"),
        ],
    },
    "Figma": {
        "category": "设计协作", "url": "https://figma.com",
        "logo": "https://static.figma.com/favicon.svg", "status": "active",
        "sources": [
            ("homepage", "官网首页", "https://www.figma.com"),
            ("status", "服务状态页", "https://status.figma.com"),
            ("blog", "官方博客", "https://www.figma.com/blog/feed/"),
            ("rss", "RSS 订阅", "https://www.figma.com/blog/feed/"),
        ],
    },
    "Anthropic": {
        "category": "AI 助手", "url": "https://anthropic.com",
        "logo": "https://www.anthropic.com/favicon.ico", "status": "active",
        "sources": [
            ("homepage", "官网首页", "https://www.anthropic.com"),
            ("changelog", "更新日志", "https://www.anthropic.com/news"),
            ("pricing", "定价页", "https://www.anthropic.com/pricing"),
            ("docs", "帮助文档", "https://docs.anthropic.com"),
        ],
    },
    "Suno": {
        "category": "AI 音乐", "url": "https://suno.com",
        "logo": "https://suno.com/favicon.ico", "status": "paused",
        "sources": [
            ("homepage", "官网首页", "https://suno.com"),
            ("changelog", "更新日志", "https://suno.com/changelog"),
        ],
    },
    "Linear": {
        "category": "项目管理", "url": "https://linear.app",
        "logo": "https://linear.app/favicon.ico", "status": "active",
        "sources": [
            ("homepage", "官网首页", "https://linear.app"),
            ("changelog", "更新日志", "https://linear.app/changelog"),
            ("docs", "帮助文档", "https://linear.app/docs"),
            ("custom", "自定义页面", "https://marketplace.linear.app"),
        ],
    },
    "Vercel": {
        "category": "开发部署", "url": "https://vercel.com",
        "logo": "https://vercel.com/favicon.ico", "status": "active",
        "sources": [
            ("homepage", "官网首页", "https://vercel.com"),
            ("status", "服务状态页", "https://www.vercel-status.com"),
            ("blog", "官方博客", "https://vercel.com/blog/rss.xml"),
            ("docs", "帮助文档", "https://vercel.com/docs"),
        ],
    },
    "Cloudflare": {
        "category": "基础设施", "url": "https://cloudflare.com",
        "logo": "https://www.cloudflare.com/favicon.ico", "status": "active",
        "sources": [
            ("homepage", "官网首页", "https://www.cloudflare.com"),
            ("status", "服务状态页", "https://www.cloudflarestatus.com"),
            ("rss", "RSS 订阅", "https://blog.cloudflare.com/rss/"),
            ("docs", "帮助文档", "https://developers.cloudflare.com"),
        ],
    },
    "DeepSeek": {
        "category": "AI 助手", "url": "https://deepseek.com",
        "logo": "https://www.deepseek.com/favicon.ico", "status": "active",
        "sources": [
            ("homepage", "官网首页", "https://www.deepseek.com"),
            ("changelog", "更新日志", "https://www.deepseek.com/news"),
            ("pricing", "定价页", "https://platform.deepseek.com/pricing"),
            ("app_store", "应用商店页", "https://apps.apple.com/app/id1660455256"),
        ],
    },
    "通义千问": {
        "category": "AI 助手", "url": "https://tongyi.aliyun.com",
        "logo": "https://tongyi.aliyun.com/favicon.ico", "status": "active",
        "sources": [
            ("homepage", "官网首页", "https://tongyi.aliyun.com"),
            ("app_store", "应用商店页", "https://apps.apple.com/app/id6466739875"),
            ("docs", "帮助文档", "https://help.aliyun.com/zh/model-studio"),
        ],
    },
    "语雀": {
        "category": "知识库", "url": "https://yuque.com",
        "logo": "https://www.yuque.com/favicon.ico", "status": "active",
        "deleted": True,  # 演示：该竞品已在回收站
        "sources": [
            ("homepage", "官网首页", "https://www.yuque.com"),
            ("changelog", "更新日志", "https://www.yuque.com/changelog"),
        ],
    },
    "Trello": {
        "category": "项目管理", "url": "https://trello.com",
        "logo": "https://trello.com/favicon.ico", "status": "paused",
        "sources": [
            ("homepage", "官网首页", "https://trello.com"),
            ("status", "服务状态页", "https://www.trellostatus.com"),
            ("blog", "官方博客", "https://blog.trello.com/feed"),
        ],
    },
    "Zoom": {
        "category": "音视频会议", "url": "https://zoom.us",
        "logo": "https://zoom.us/favicon.ico", "status": "active",
        "sources": [
            ("homepage", "官网首页", "https://www.zoom.us"),
            ("pricing", "定价页", "https://www.zoom.us/pricing"),
            ("status", "服务状态页", "https://status.zoom.us"),
        ],
    },
}

# 每个监控源的健康度覆盖（无条目的源落到 success）
SRC_META: dict[tuple[str, str], dict] = {
    ("Suno", "官网首页"): {"last_status": "success", "enabled": True, "fail_count": 0},
    ("Suno", "更新日志"): {"last_status": "failed", "enabled": False, "fail_count": 5},
    ("Vercel", "服务状态页"): {"last_status": "failed", "enabled": True, "fail_count": 2},
    ("Cloudflare", "官网首页"): {"last_status": "failed", "enabled": True, "fail_count": 1},
    ("Figma", "官方博客"): {"last_status": "success", "enabled": True, "fail_count": 0},
}


# ---------------------------------------------------------------------------
# 情报事件：覆盖全部 5 类 event_type × 高/中/低优先级
# ---------------------------------------------------------------------------
EVENTS: list[dict] = [
    {"competitor": "Notion", "source": "更新日志", "event_type": "new_feature",
     "title": "Notion 上线 Custom Agents 自动化工作流", "priority": "high", "days_ago": 1,
     "summary": "更新日志新增 Custom Agents 能力，支持把常用 AI 任务编排成可复用的自动化流程。",
     "ai_analysis": "Notion 继续押注 AI Agent 方向，与头部协作文档拉开差距，关注后续付费转化。"},
    {"competitor": "Notion", "source": "定价页", "event_type": "price_change",
     "title": "Notion 企业版计费调整", "priority": "mid", "days_ago": 2,
     "summary": "定价页企业版说明更新，团队席位计费方式发生变化。",
     "ai_analysis": "计费结构往席位与用量混合方向演进，可能推高企业客户客单价。"},
    {"competitor": "Figma", "source": "官网首页", "event_type": "content_update",
     "title": "Figma 首页新增交互式原型演示模块", "priority": "mid", "days_ago": 1,
     "summary": "首页主视觉新增交互式原型演示模块，突出实时协作能力。",
     "ai_analysis": "强化交互原型卖点，对应 Miro/Lucid 的压力。"},
    {"competitor": "Figma", "source": "服务状态页", "event_type": "public_sentiment",
     "title": "Figma 状态页显示服务恢复正常", "priority": "low", "days_ago": 3,
     "summary": "服务状态页新增一条 Incidents 记录并标记 resolved。",
     "ai_analysis": "服务稳定性良好，短期无舆情风险。"},
    {"competitor": "Anthropic", "source": "更新日志", "event_type": "new_feature",
     "title": "Anthropic 发布 Claude Code 新版本", "priority": "high", "days_ago": 0,
     "summary": "Claude Code 更新日志新增子代理并行处理与工具调用改进。",
     "ai_analysis": "在编程智能体赛道加速迭代，竞争压力加大。"},
    {"competitor": "Anthropic", "source": "定价页", "event_type": "price_change",
     "title": "Anthropic 调整 API 用量单价", "priority": "high", "days_ago": 2,
     "summary": "定价页输入/输出 token 单价更新，长上下文计费说明被重写。",
     "ai_analysis": "价格下行将刺激 API 调用量，长期观察对利润率影响。"},
    {"competitor": "Suno", "source": "更新日志", "event_type": "new_feature",
     "title": "Suno 发布通用音色自动识别", "priority": "low", "days_ago": 5,
     "summary": "更新日志新增 App 内对任意音频的音色识别功能。",
     "ai_analysis": "功能更新幅度较小，属于常规迭代。"},
    {"competitor": "Linear", "source": "更新日志", "event_type": "new_feature",
     "title": "Linear 加入自定义视图过滤条件", "priority": "mid", "days_ago": 1,
     "summary": "更新日志新增自定义视图，可按任意字段组合过滤。",
     "ai_analysis": "继续强化工程团队的使用深度，对竞品形成持续压制。"},
    {"competitor": "Vercel", "source": "服务状态页", "event_type": "public_sentiment",
     "title": "Vercel 状态页显示部分区域部署延迟", "priority": "high", "days_ago": 0,
     "summary": "服务状态页新增 Major 级别 Deployments 延迟，当前 Investigating。",
     "ai_analysis": "核心部署链路出现高影响事故，对用户信任有短期影响，需重点观察恢复时间。"},
    {"competitor": "Cloudflare", "source": "服务状态页", "event_type": "public_sentiment",
     "title": "Cloudflare 状态页显示历史故障已解决", "priority": "low", "days_ago": 6,
     "summary": "服务状态页回填了一条 Minor 级别历史记录，已 Resolved。",
     "ai_analysis": "已解决，无持续影响。"},
    {"competitor": "DeepSeek", "source": "官网首页", "event_type": "other",
     "title": "DeepSeek 官网完成品牌视觉改版", "priority": "mid", "days_ago": 3,
     "summary": "官网首页视觉风格与 Slogan 发生调整，整体更强调深度推理能力。",
     "ai_analysis": "品牌叙事从通用助手转向「深度推理」，可能配合模型定位调整。"},
    {"competitor": "通义千问", "source": "应用商店页", "event_type": "other",
     "title": "通义千问 App 发布新版本", "priority": "mid", "days_ago": 4,
     "summary": "应用商店页版本号更新，说明新增文档解析与多端同步。",
     "ai_analysis": "App 端功能补强，提升 C 端留存。"},
    {"competitor": "Trello", "source": "官方博客", "event_type": "content_update",
     "title": "Trello 发布模板中心推广文章", "priority": "low", "days_ago": 7,
     "summary": "官方博客更新一篇模板中心介绍，强调团队协作效率。",
     "ai_analysis": "属于常规内容运营，无产品层面变化。"},
    {"competitor": "Zoom", "source": "定价页", "event_type": "price_change",
     "title": "Zoom 套餐价格上涨", "priority": "high", "days_ago": 2,
     "summary": "定价页 Business/Enterprise 套餐价格上调，并新增 AI Companion 加购项。",
     "ai_analysis": "变现节奏加速，可能流失部分价格敏感的中小团队。"},
]

# 事件成功快照之外，额外补一些特殊快照（失败 / 无变化）
EXTRA_SNAPSHOTS: list[dict] = [
    {"competitor": "Cloudflare", "source": "官网首页", "ok": False, "http_status": 404,
     "fail_reason": "HTTP 404 Not Found", "days_ago": 1},
    {"competitor": "Figma", "source": "官网首页", "ok": True, "http_status": 200,
     "change_detected": False, "days_ago": 1},
]


# ---------------------------------------------------------------------------
# 抓取日志：success / failed(404,5xx,超时) / skipped，手动 + 定时
# ---------------------------------------------------------------------------
CRAWL_LOGS: list[dict] = [
    {"competitor": "Notion", "source": "官网首页", "status": STATUS_SUCCESS, "trigger": TRIGGER_SCHEDULER,
     "http_status": 200, "changed": False, "first_time": True, "event_created": False, "days_ago": 1},
    {"competitor": "Notion", "source": "更新日志", "status": STATUS_SUCCESS, "trigger": TRIGGER_SCHEDULER,
     "http_status": 200, "changed": True, "first_time": False, "event_created": True, "days_ago": 1},
    {"competitor": "Notion", "source": "定价页", "status": STATUS_SUCCESS, "trigger": TRIGGER_MANUAL,
     "http_status": 200, "changed": False, "first_time": False, "event_created": False, "days_ago": 2},
    {"competitor": "Figma", "source": "官网首页", "status": STATUS_SUCCESS, "trigger": TRIGGER_SCHEDULER,
     "http_status": 200, "changed": True, "first_time": False, "event_created": False, "days_ago": 1},
    {"competitor": "Figma", "source": "服务状态页", "status": STATUS_SUCCESS, "trigger": TRIGGER_SCHEDULER,
     "http_status": 200, "changed": True, "first_time": False, "event_created": True, "days_ago": 3},
    {"competitor": "Figma", "source": "官方博客", "status": STATUS_SUCCESS, "trigger": TRIGGER_SCHEDULER,
     "http_status": 200, "changed": False, "first_time": False, "event_created": False, "days_ago": 1},
    {"competitor": "Anthropic", "source": "官网首页", "status": STATUS_SUCCESS, "trigger": TRIGGER_SCHEDULER,
     "http_status": 200, "changed": True, "first_time": False, "event_created": True, "days_ago": 0},
    {"competitor": "Anthropic", "source": "更新日志", "status": STATUS_SUCCESS, "trigger": TRIGGER_SCHEDULER,
     "http_status": 200, "changed": False, "first_time": False, "event_created": False, "days_ago": 0},
    {"competitor": "Suno", "source": "更新日志", "status": STATUS_SKIPPED, "trigger": TRIGGER_SCHEDULER,
     "http_status": None, "changed": False, "first_time": False, "event_created": False, "days_ago": 1,
     "error": "监控源已停用，跳过抓取"},
    {"competitor": "Linear", "source": "更新日志", "status": STATUS_SUCCESS, "trigger": TRIGGER_SCHEDULER,
     "http_status": 200, "changed": True, "first_time": False, "event_created": True, "days_ago": 1},
    {"competitor": "Vercel", "source": "服务状态页", "status": STATUS_FAILED, "trigger": TRIGGER_SCHEDULER,
     "http_status": 500, "changed": False, "first_time": False, "event_created": False, "days_ago": 0,
     "error": "HTTP 500 Internal Server Error"},
    {"competitor": "Cloudflare", "source": "官网首页", "status": STATUS_FAILED, "trigger": TRIGGER_MANUAL,
     "http_status": 404, "changed": False, "first_time": False, "event_created": False, "days_ago": 1,
     "error": "HTTP 404 Not Found"},
    {"competitor": "DeepSeek", "source": "官网首页", "status": STATUS_SUCCESS, "trigger": TRIGGER_SCHEDULER,
     "http_status": 200, "changed": True, "first_time": False, "event_created": False, "days_ago": 3},
    {"competitor": "通义千问", "source": "应用商店页", "status": STATUS_SUCCESS, "trigger": TRIGGER_SCHEDULER,
     "http_status": 200, "changed": True, "first_time": False, "event_created": True, "days_ago": 4},
    {"competitor": "Trello", "source": "官方博客", "status": STATUS_SUCCESS, "trigger": TRIGGER_SCHEDULER,
     "http_status": 200, "changed": False, "first_time": False, "event_created": False, "days_ago": 7},
    {"competitor": "Zoom", "source": "定价页", "status": STATUS_FAILED, "trigger": TRIGGER_SCHEDULER,
     "http_status": None, "changed": False, "first_time": False, "event_created": False, "days_ago": 1,
     "error": "network error: connect timeout (15s)"},
    {"competitor": "语雀", "source": "官网首页", "status": STATUS_SUCCESS, "trigger": TRIGGER_SCHEDULER,
     "http_status": 200, "changed": False, "first_time": True, "event_created": False, "days_ago": 9},
]

# 趋势方向覆盖（未列出的竞品走 stable）
TREND_DIR: dict[str, TrendDirection] = {
    "Notion": TrendDirection.RISING,
    "Anthropic": TrendDirection.RISING,
    "Linear": TrendDirection.RISING,
    "Vercel": TrendDirection.RISING,
    "DeepSeek": TrendDirection.RISING,
    "Trello": TrendDirection.DECLINING,
    "Suno": TrendDirection.DECLINING,
}


def _type_label(etype: str) -> tuple[str, str]:
    return TYPE_META.get(etype, TYPE_META["other"])


def build_report_payload(total_events: int, competitor_count: int) -> dict:
    from datetime import date

    today = date.today()
    range_start = today - timedelta(days=6)
    impact = [0] * 7
    impact[-1] = total_events

    stat_map: dict[str, dict] = {}
    rank_map: dict[str, int] = {}
    ai = 0
    for e in EVENTS:
        label, _tt = _type_label(e["event_type"])
        stat_map[label] = {"label": label, "value": stat_map.get(label, {"value": 0})["value"] + 1}
        rank_map[e["competitor"]] = rank_map.get(e["competitor"], 0) + 1
        if e["priority"] == "high":
            ai += 1

    stats = [
        {"key": "events", "label": "重要变化事件", "value": total_events, "delta": total_events * 100,
         "deltaType": "up"},
        {"key": "competitors", "label": "涉及竞品", "value": competitor_count, "delta": competitor_count * 100,
         "deltaType": "up"},
    ]
    label2key = {lbl: kw for kw, (lbl, _) in TYPE_META.items()}
    for lbl, it in stat_map.items():
        stats.append({"key": label2key[lbl], "label": lbl, "value": it["value"], "delta": 0, "deltaType": "up"})
    stats.append({"key": "impact", "label": "高影响事件", "value": ai, "delta": ai * 100, "deltaType": "up"})

    highlights = []
    for i, e in enumerate(EVENTS[:4], start=1):
        label, tag = _type_label(e["event_type"])
        highlights.append({
            "id": i, "title": e["title"], "tag": label, "tagType": tag,
            "impact": PRIORITY_LABEL[e["priority"]], "impactType": e["priority"],
            "points": [e["summary"]], "affected": [],
            "foundAt": (datetime.now(TZ) - timedelta(days=e["days_ago"])).strftime("%Y-%m-%d %H:%M"),
            "aiConfidence": 92,
        })

    rank_sorted = sorted(rank_map.items(), key=lambda kv: kv[1], reverse=True)
    related_events = [
        {"id": i, "brand": e["competitor"], "title": e["title"],
         "tag": _type_label(e["event_type"])[0], "tagType": _type_label(e["event_type"])[1],
         "time": (datetime.now(TZ) - timedelta(days=e["days_ago"])).strftime("%Y-%m-%d %H:%M")}
        for i, e in enumerate(EVENTS[:4], start=1)
    ]
    related_competitors = [
        {"name": c, "domain": PLAN[c]["url"].replace("https://", ""), "iconText": c[0],
         "iconBg": "#e6f2ff", "iconColor": "#1677ff", "changes": rank_map.get(c, 0)}
        for c in PLAN if not PLAN[c].get("deleted")
    ]

    total_sources = sum(len(p["sources"]) for p in PLAN.values() if not p.get("deleted"))
    return {
        "stats": stats,
        "highlights": highlights,
        "categoryDist": [{"name": lbl, "value": it["value"]} for lbl, it in stat_map.items()],
        "competitorRank": [{"name": c, "value": v} for c, v in rank_sorted],
        "impactTrend": {
            "dates": [(range_start + timedelta(days=i)).strftime("%m/%d") for i in range(7)],
            "current": impact, "previous": [0] * 7,
        },
        "relatedEvents": related_events,
        "relatedCompetitors": related_competitors,
        "aiSteps": [
            {"title": "数据采集", "desc": f"从 {total_sources} 个监控页面抓取竞品公开信息。",
             "time": f"{range_start} 06:00"},
            {"title": "事件识别", "desc": f"从采集内容中识别出 {total_events} 条有效变化事件，并完成去重与分类。",
             "time": f"{range_start} 06:12"},
            {"title": "影响评估", "desc": f"结合历史数据评估影响等级，标记 {ai} 条高影响事件。",
             "time": f"{range_start} 06:20"},
            {"title": "报告生成", "desc": "汇总核心摘要、重点变化与统计数据，生成本期竞品周报。",
             "time": f"{range_start} 06:30"},
        ],
    }


async def _clear_user_data(db, uid: int) -> None:
    """清空该用户此前的模拟数据（模拟数据可整体丢弃）。"""
    comp_ids = [
        r[0] for r in (await db.execute(select(Competitor.id).where(Competitor.user_id == uid))).all()
    ]
    await db.execute(delete(CrawlLog).where(CrawlLog.user_id == uid))
    await db.execute(delete(WeeklyReport).where(WeeklyReport.user_id == uid))
    await db.execute(delete(EventRead).where(EventRead.user_id == uid))
    if comp_ids:
        await db.execute(
            delete(IntelligenceEvent).where(IntelligenceEvent.competitor_id.in_(comp_ids))
        )
        await db.execute(delete(PageSnapshot).where(PageSnapshot.competitor_id.in_(comp_ids)))
        await db.execute(delete(TrendInsight).where(TrendInsight.competitor_id.in_(comp_ids)))
        await db.execute(delete(MonitorSource).where(MonitorSource.competitor_id.in_(comp_ids)))
        await db.execute(delete(Competitor).where(Competitor.user_id == uid))


async def seed(user_ref: str) -> None:
    from app.core.source_registry import SourceType, get_source_config
    from app.models.competitor import CompetitorStatus

    async with SessionLocal() as db:
        user = (
            await db.execute(select(User).where(User.username == user_ref))
        ).scalar_one_or_none()
        if user is None:
            user = (
                await db.execute(select(User).where(User.id == int(user_ref)))
            ).scalar_one_or_none()
        if user is None:
            print(f"未找到用户: {user_ref}")
            return
        uid = user.id
        print(f"目标用户 id={uid} username={user.username}")

        await _clear_user_data(db, uid)
        await db.commit()
        print("已清空该用户此前的模拟数据。")

        status_by_name = {"active": CompetitorStatus.ACTIVE, "paused": CompetitorStatus.PAUSED}
        comp_map: dict[str, Competitor] = {}
        src_map: dict[tuple[str, str], MonitorSource] = {}
        inserted_event_ids: list[int] = []

        # ---- 竞品 + 监控源 ----
        for name, p in PLAN.items():
            comp = Competitor(
                user_id=uid, name=name, official_url=p["url"],
                category=p["category"], logo_url=p["logo"],
                status=status_by_name[p["status"]],
                deleted_at=dt(10) if p.get("deleted") else None,
                created_at=dt(14),
            )
            db.add(comp)
            await db.flush()
            comp_map[name] = comp
            for stype, sname, surl in p["sources"]:
                st = SourceType(stype)
                cfg = get_source_config(st)
                meta = SRC_META.get((name, sname), {
                    "last_status": "success", "enabled": True, "fail_count": 0})
                src = MonitorSource(
                    competitor_id=comp.id, source_type=st, name=sname, url=surl,
                    render_mode=cfg.render, interval_minutes=cfg.default_interval_minutes,
                    enabled=meta["enabled"], last_crawled_at=dt(1),
                    last_status=meta["last_status"], fail_count=meta["fail_count"],
                    created_at=dt(14),
                )
                db.add(src)
                await db.flush()
                src_map[(name, sname)] = src
        print(f"已种入竞品 {len(comp_map)} 个，监控源 {len(src_map)} 个")

        # ---- 情报事件（含快照）+ 补充特殊快照 ----
        for ev in EVENTS:
            src = src_map[(ev["competitor"], ev["source"])]
            comp = comp_map[ev["competitor"]]
            snap = PageSnapshot(
                competitor_id=comp.id, source_id=src.id, source_type=src.source_type,
                url=src.url, content_hash="mock-" + ev["title"][:24], http_status=200,
                is_success=True, change_detected=True,
                diff_text="--- 上次\n+++ 本次\n" + ev["summary"],
                crawled_at=dt(ev["days_ago"], 10),
            )
            db.add(snap)
            await db.flush()
            event = IntelligenceEvent(
                competitor_id=comp.id, source_id=src.id, snapshot_id=snap.id,
                event_type=ev["event_type"], title=ev["title"], summary=ev["summary"],
                ai_analysis=ev["ai_analysis"], diff_detail="--- 上次\n+++ 本次\n" + ev["summary"],
                keywords=["mock", ev["event_type"]], confidence=0.9, priority=ev["priority"],
                created_at=dt(ev["days_ago"], 10),
            )
            db.add(event)
            await db.flush()
            inserted_event_ids.append(event.id)

        for sp in EXTRA_SNAPSHOTS:
            src = src_map[(sp["competitor"], sp["source"])]
            comp = comp_map[sp["competitor"]]
            db.add(PageSnapshot(
                competitor_id=comp.id, source_id=src.id, source_type=src.source_type,
                url=src.url, http_status=sp["http_status"],
                is_success=sp.get("ok", True),
                fail_reason=sp.get("fail_reason"),
                change_detected=sp.get("change_detected", False), crawled_at=dt(sp["days_ago"], 11),
            ))
        print(f"已种入情报事件 {len(EVENTS)} 条，快照 {len(EVENTS) + len(EXTRA_SNAPSHOTS)} 条")

        # ---- 通知未读标记：给 3 条高优事件写未读 ----
        picked = [e for e in EVENTS if e["priority"] == "high"][:3]
        for i, ev in enumerate(picked):
            event_id = inserted_event_ids[EVENTS.index(ev)]
            db.add(EventRead(
                user_id=uid, event_id=event_id, is_read=False, read_at=None,
                created_at=dt(ev["days_ago"]),
            ))
        print(f"已写入未读通知标记 {len(picked)} 条")

        # ---- 抓取日志 ----
        for lg in CRAWL_LOGS:
            src = src_map[(lg["competitor"], lg["source"])]
            comp = comp_map[lg["competitor"]]
            db.add(CrawlLog(
                user_id=uid, competitor_id=comp.id, competitor_name=comp.name,
                source_id=src.id, source_name=src.name, source_type=src.source_type,
                url=src.url, trigger=lg["trigger"], status=lg["status"],
                http_status=lg["http_status"], changed=lg["changed"],
                first_time=lg["first_time"], event_created=lg["event_created"],
                duration_ms=1200 if lg["status"] == STATUS_FAILED else 2400,
                error=lg.get("error"), created_at=dt(lg["days_ago"]),
            ))
        print(f"已种入抓取日志 {len(CRAWL_LOGS)} 条")

        # ---- 趋势判断（三方向覆盖）----
        for name, comp in comp_map.items():
            direction = TREND_DIR.get(name, TrendDirection.STABLE)
            db.add(TrendInsight(
                competitor_id=comp.id, period_days=30, direction=direction,
                summary=f"{name} 近 30 天整体趋势为「{direction.value}」。",
                highlights=["功能迭代提速", "定价策略调整"]
                if direction == TrendDirection.RISING
                else (["迭代节奏放缓"] if direction == TrendDirection.DECLINING
                      else ["整体平稳", "偶发内容更新"]),
                event_count=2, high_impact_count=1, coverage_days=30,
                created_at=dt(1),
            ))
        print(f"已种入趋势判断 {len(comp_map)} 条")

        # ---- 报告：周报/月报 × 收藏/分享/回收站 ----
        now = datetime.now(TZ)
        today = now.date()
        week_start = today - timedelta(days=today.weekday())
        payload = build_report_payload(len(EVENTS), sum(
            1 for p in PLAN.values() if not p.get("deleted")))
        week_no = today.isocalendar().week

        # 1) 本周周报（收藏）
        db.add(WeeklyReport(
            user_id=uid, report_type="weekly",
            title=f"{today.year}年第{week_no}周 竞品周报",
            range_start=week_start, range_end=today,
            competitor_count=len(comp_map), event_count=len(EVENTS), favorite=True,
            summary="本周监控到若干功能更新与价格调整，整体活跃度上升。",
            content="## 本周要点\n\n" + "\n\n".join(
                f"- **{e['title']}**：{e['summary']}" for e in EVENTS[:4]),
            payload=payload, created_at=dt(1),
        ))
        # 2) 上周周报（普通）
        db.add(WeeklyReport(
            user_id=uid, report_type="weekly",
            title=f"{today.year}年第{week_no - 1}周 竞品周报",
            range_start=week_start - timedelta(days=7), range_end=week_start - timedelta(days=1),
            competitor_count=len(comp_map), event_count=8, favorite=False,
            summary="上周整体平稳，仅个别竞品有内容更新。",
            content="## 上周要点\n\n整体变化较少，重点内容已归档。",
            payload=payload, created_at=dt(8),
        ))
        # 3) 本月月报（收藏 + 免登录分享链接）
        db.add(WeeklyReport(
            user_id=uid, report_type="monthly",
            title=f"{today.year}年{today.month}月 竞品月报",
            range_start=today.replace(day=1), range_end=today,
            competitor_count=len(comp_map), event_count=len(EVENTS), favorite=True,
            share_token=secrets.token_hex(24),
            share_expires_at=now + timedelta(days=7),
            summary="本月重点竞品持续迭代，AI 方向竞争加剧。",
            content="## 月度汇总\n\n本月共监控到多条有效变化，整体节奏平稳偏上升。",
            payload=payload, created_at=dt(15),
        ))
        # 4) 本月周报（已移入回收站：软删除）
        db.add(WeeklyReport(
            user_id=uid, report_type="weekly",
            title=f"{today.year}年第{week_no}周 周报（草稿，已删除）",
            range_start=week_start, range_end=today,
            competitor_count=len(comp_map), event_count=len(EVENTS), favorite=False,
            deleted_at=dt(2),
            summary="这篇周报已被删除，仅出现在回收站。",
            content="## 已删除\n\n该报告已在回收站。", payload=payload, created_at=dt(4),
        ))
        # 5) 上月月报（已移入回收站）
        db.add(WeeklyReport(
            user_id=uid, report_type="monthly",
            title=f"{today.year}年{today.month - 1 if today.month > 1 else 12}月 竞品月报",
            range_start=(today.replace(day=1) - timedelta(days=2)).replace(day=1),
            range_end=today.replace(day=1) - timedelta(days=1),
            competitor_count=len(comp_map), event_count=6, favorite=False,
            deleted_at=dt(30),
            summary="已删除的月度报告。",
            content="## 已删除\n\n该报告已在回收站。", payload=payload, created_at=dt(32),
        ))
        print("已种入周报 ×3、月报 ×2（含收藏/分享/回收站各场景）")

        await db.commit()
        print("提交完成。")


async def main() -> None:
    ref = sys.argv[1] if len(sys.argv) > 1 else "3916408482"
    await seed(ref)


if __name__ == "__main__":
    asyncio.run(main())