/**
 * 共享内存数据库（vite-plugin-mock 每个 mock 文件会被 esbuild 独立打包，
 * 普通 import 的模块会被内联复制、状态不共享；跨文件共享的可变状态必须挂到
 * globalThis 上）。这里导出的都是纯函数，状态统一通过 db() 经 globalThis 访问。
 */

// ---------- 数据源类型注册表（与后端 SOURCE_TYPE_REGISTRY 对齐） ----------
export const SOURCE_TYPES = [
  { type: "homepage", label: "官网首页", render: "browser", defaultIntervalMinutes: 1440, llmHint: "官网首页内容变化" },
  { type: "pricing", label: "定价页", render: "browser", defaultIntervalMinutes: 1440, llmHint: "定价/套餐/计费调整" },
  { type: "changelog", label: "更新日志", render: "browser", defaultIntervalMinutes: 1440, llmHint: "新版本/新功能/修复" },
  { type: "blog", label: "官方博客", render: "http", defaultIntervalMinutes: 1440, llmHint: "官方文章发布" },
  { type: "docs", label: "帮助文档", render: "browser", defaultIntervalMinutes: 10080, llmHint: "文档内容变更" },
  { type: "status", label: "服务状态页", render: "browser", defaultIntervalMinutes: 60, llmHint: "故障/维护公告" },
  { type: "rss", label: "RSS 订阅", render: "http", defaultIntervalMinutes: 60, llmHint: "订阅源条目变化" },
  { type: "app_store", label: "应用商店页", render: "browser", defaultIntervalMinutes: 1440, llmHint: "版本更新/评分波动" },
  { type: "custom", label: "自定义页面", render: "browser", defaultIntervalMinutes: 1440, llmHint: "" },
] as const;

export function sourceLabel(type: string): string {
  const found = SOURCE_TYPES.find((t) => t.type === type);
  return found ? found.label : type;
}

// ---------- 事件分类 / 标签 / 优先级 ----------
export const EVENT_TYPES: Record<string, { label: string; category: string; tagType: string }> = {
  new_feature: { label: "功能更新", category: "feature", tagType: "tag-new" },
  price_change: { label: "价格变化", category: "price", tagType: "tag-price" },
  content_update: { label: "内容更新", category: "content", tagType: "tag-update" },
  public_sentiment: { label: "舆论动态", category: "negative", tagType: "tag-negative" },
  other: { label: "其他", category: "other", tagType: "tag-other" },
};

export const PRIORITY_LABELS: Record<string, string> = { high: "高", mid: "中", low: "低" };

const ICON_TONES: [string, string][] = [
  ["#e6f7f0", "#10a37f"],
  ["#e8f0fe", "#4285f4"],
  ["#f5e8df", "#c96442"],
  ["#e6faff", "#13c2c2"],
  ["#f0e9ff", "#6b32d9"],
  ["#fff3e6", "#fa8c16"],
];

export function cleanHost(url?: string | null): string {
  const host = (url || "").replace(/^https?:\/\//i, "").split("/")[0].trim();
  return host.replace(/^www\./i, "");
}

export function iconTone(key: string): [string, string] {
  let sum = 0;
  for (let i = 0; i < (key || "?").length; i += 1) sum += (key || "?").charCodeAt(i);
  return ICON_TONES[sum % ICON_TONES.length];
}

export function iconText(name: string): string {
  return ((name || "?").trim()[0] || "?").toUpperCase();
}

// ---------- 时间助手（本地时区，与后端 Asia/Shanghai 一致） ----------
function pad(n: number): string {
  return String(n).padStart(2, "0");
}

export function isoDate(d: Date): string {
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

export function isoTime(d: Date): string {
  return `${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export function isoDateTime(d: Date): string {
  return `${isoDate(d)} ${isoTime(d)}`;
}

export function formatDateTime(iso: string): string {
  return isoDateTime(new Date(iso));
}

export function humanizeAgo(iso: string, empty = "从未抓取"): string {
  if (!iso) return empty;
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "刚刚";
  if (mins < 60) return `${mins} 分钟前`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours} 小时前`;
  const days = Math.floor(hours / 24);
  return `${days} 天前`;
}

export function dateLabel(iso: string): string {
  const d = new Date(iso);
  const today = new Date();
  const yesterday = new Date(Date.now() - 86400000);
  const ds = isoDate(d);
  if (ds === isoDate(today)) return "今天";
  if (ds === isoDate(yesterday)) return "昨天";
  return ds;
}

function humanizeInterval(minutes: number): string {
  const units: [number, string][] = [
    [10080, "周"],
    [1440, "天"],
    [60, "小时"],
  ];
  for (const [unit, name] of units) {
    if (minutes % unit === 0) {
      const count = minutes / unit;
      return count === 1 ? `每${name}` : `每 ${count} ${name}`;
    }
  }
  return `每 ${minutes} 分钟`;
}

// ---------- 响应壳 ----------
export function ok(data: unknown) {
  return { code: 0, message: "ok", data };
}

export function err(code: number, message: string) {
  return { code, message, data: null };
}

/** 从请求 URL 里取最后一个纯数字段作为路径参数 id（PATH+query 共存时 query 里拿不到） */
export function idFrom(url: string): number {
  const seg = url.split("?")[0].split("/").filter((s) => /^\d+$/.test(s));
  return Number(seg[seg.length - 1] ?? 0);
}

// ---------- 内存库（通过 globalThis 跨文件共享） ----------

interface DB {
  users: any[];
  tokens: Record<string, number>;
  competitors: any[];
  events: any[];
  reports: any[];
  crawlLogs: any[];
  eventReads: any[];
  providers: any[];
  emailCodes: Record<string, string>;
  llmSetting: Record<string, any>;
  systemSettings: Record<string, any>;
  seq: Record<string, number>;
}

function createDB(): DB {
  const now = Date.now();
  const hoursAgo = (h: number) => new Date(now - h * 3600000).toISOString();
  const daysAgo = (d: number) => new Date(now - d * 86400000).toISOString();

  const users: any[] = [
    {
      id: 1,
      username: "1614910065",
      name: "管理员",
      password: "123456",
      email: "1614910065@qq.com",
      avatar: "",
      isAdmin: true,
      active: true,
      preferences: { allowUnreachableOfficial: false, defaultSourceTypes: ["homepage"] },
    },
    {
      id: 2,
      username: "demo",
      name: "Demo用户",
      password: "123456",
      email: "demo@example.com",
      avatar: "",
      isAdmin: false,
      active: true,
      preferences: { allowUnreachableOfficial: true, defaultSourceTypes: ["homepage", "pricing"] },
    },
    {
      id: 3,
      username: "demo1",
      name: "Demo1用户",
      password: "123456",
      email: "demo1@example.com",
      avatar: "",
      isAdmin: false,
      active: true,
      preferences: { allowUnreachableOfficial: true, defaultSourceTypes: ["homepage", "pricing"] },
    },
    {
      id: 4,
      username: "demo2",
      name: "Demo2用户",
      password: "123456",
      email: "demo2@example.com",
      avatar: "",
      isAdmin: false,
      active: true,
      preferences: { allowUnreachableOfficial: true, defaultSourceTypes: ["homepage", "pricing"] },
    },
  ];

  let sourceId = 1;
  const mkSource = (competitorId: number, type: string, opts: any = {}) => {
    const cfg = SOURCE_TYPES.find((t) => t.type === type)!;
    return {
      id: sourceId++,
      competitorId,
      sourceType: type,
      name: opts.name ?? cfg.label,
      url: opts.url ?? "",
      renderMode: cfg.render,
      intervalMinutes: opts.intervalMinutes ?? cfg.defaultIntervalMinutes,
      enabled: opts.enabled ?? true,
      lastStatus: opts.lastStatus ?? "success",
      lastError: opts.lastError ?? null,
      failCount: opts.failCount ?? 0,
      lastCrawledAt: opts.lastCrawledAt ?? null,
    };
  };

  // 竞品：name / officialUrl / category / status / 停止/异常需要的源数据
  // uid：归属用户（1=管理员，2=demo，3=demo1），演示「全部竞品」页的跨用户视图
  const comps = [
    { name: "Notion", host: "notion.so", cat: "SaaS工具", uid: 2, status: "active", hours: 2, changes: 5, today: 2 },
    { name: "飞书", host: "feishu.cn", cat: "SaaS工具", uid: 3, status: "active", hours: 5, changes: 8, today: 3 },
    { name: "ChatGPT", host: "openai.com", cat: "AI产品", status: "active", hours: 1, changes: 12, today: 4 },
    { name: "Keep", host: "keep.com", cat: "运动健身", status: "active", hours: 3, changes: 3, today: 1 },
    { name: "Canva", host: "canva.com", cat: "SaaS工具", status: "active", hours: 8, changes: 2, today: 0, failed: true },
    { name: "Figma", host: "figma.com", cat: "设计工具", status: "paused", hours: 24, changes: 0, today: 0 },
    { name: "腾讯文档", host: "docs.qq.com", cat: "协作办公", status: "active", hours: 48, changes: 0, today: 0 },
    { name: "钉钉", host: "dingtalk.com", cat: "协作办公", status: "active", hours: 48, changes: 0, today: 0 },
  ];

  const competitorType = (cat: string): string =>
    cat === "AI产品" || cat === "AI产品" || cat === "AI产品" ? "ai" : cat === "运动健身" ? "app" : cat === "设计工具" ? "tool" : "saas";

  const competitors: any[] = comps.map((c, i) => {
    const id = i + 1;
    const officialUrl = `https://www.${c.host}`;
    const base = officialUrl;
    const sources = [
      mkSource(id, "homepage", { url: base, lastCrawledAt: hoursAgo(c.hours) }),
      mkSource(id, "changelog", { url: `${base}/changelog`, lastCrawledAt: hoursAgo(c.hours) }),
      mkSource(id, "pricing", {
        url: `${base}/pricing`,
        lastCrawledAt: hoursAgo(c.hours + 1),
        ...(c.failed ? { lastStatus: "failed", lastError: "渲染超时", failCount: 1, enabled: false } : {}),
      }),
    ];
    return {
      id,
      userId: c.uid ?? 1,
      name: c.name,
      officialUrl,
      category: c.cat,
      categoryType: competitorType(c.cat),
      status: c.status,
      createdAt: daysAgo(30),
      deletedAt: null,
      restored: false,
      logoUrl: "",
      changes: c.changes,
      todayChanges: c.today,
      sources,
    };
  });

  // 事件：brand 对齐上面的竞品，覆盖 5 个分类 + 3 个优先级
  const ev = (
    id: number,
    competitorId: number,
    eventType: string,
    title: string,
    summary: string,
    priority: string,
    hours: number,
    confidence: number,
    keywords: string[],
    extra: any = {},
  ) => {
    const comp = competitors.find((c) => c.id === competitorId)!;
    const meta = EVENT_TYPES[eventType];
    const sourceName =
      eventType === "price_change" ? "定价页" : eventType === "content_update" ? "更新日志" : "官网首页";
    return {
      id,
      competitorId,
      eventType,
      title,
      summary,
      aiAnalysis: extra.aiAnalysis ?? `${comp.name} 的这项变化可能影响其市场竞争力，建议持续关注后续进展。`,
      keywords,
      confidence,
      priority,
      createdAt: hoursAgo(hours),
      sourceName,
      diffDetail: extra.diffDetail ?? null,
      sourceUrl: extra.sourceUrl ?? comp.officialUrl,
    };
  };

  const events: any[] = [
    ev(1, 3, "price_change", "OpenAI 调整了 GPT-4o 和 GPT-4o-mini 的 API 定价", "输入价格降低 20%，输出价格降低 10%。", "high", 2, 0.92, ["GPT-4o", "定价策略"]),
    ev(2, 1, "new_feature", "Notion 推出全新 AI 功能套件", "Notion AI 新增智能总结、自动翻译、任务拆解等 5 项核心能力。", "high", 4, 0.95, ["Notion AI", "功能更新"]),
    ev(3, 2, "price_change", "飞书调整企业版定价策略", "企业版基础版价格下调 15%，高级版新增安全合规模块。", "mid", 6, 0.87, ["定价", "企业版"]),
    ev(4, 5, "new_feature", "Canva 上线 AI 设计助手", "支持自然语言生成海报、PPT 与社交媒体配图。", "mid", 9, 0.9, ["AI 设计", "Canva"]),
    ev(5, 4, "content_update", "Keep 更新课程内容体系", "上线 38 门新课程，覆盖力量训练与瑜伽。", "low", 12, 0.72, ["课程", "健身"]),
    ev(6, 7, "new_feature", "腾讯文档上线 AI 会议纪要", "会议全程自动转写并生成结构化纪要与待办。", "high", 18, 0.93, ["AI 纪要", "腾讯文档"]),
    ev(7, 8, "content_update", "钉钉文档新增模板库", "一口气上线 200+ 办公模板，覆盖项目、人事、财务。", "mid", 20, 0.78, ["模板库", "钉钉"]),
    ev(8, 6, "public_sentiment", "Figma 社区出现关于订阅价格讨论", "部分用户反馈团队版涨价幅度超预期。", "low", 26, 0.68, ["订阅", "舆情"]),
    ev(9, 3, "new_feature", "ChatGPT 上线语音对话能力", "移动端支持自然的语音输入输出，延迟进一步降低。", "high", 30, 0.94, ["语音", "ChatGPT"]),
    ev(10, 1, "content_update", "Notion 更新帮助中心文档", "重写了数据库与自动化相关的使用文档。", "low", 34, 0.6, ["帮助文档", "Notion"]),
    ev(11, 2, "new_feature", "飞书多维表格新增 AI 公式", "用自然语言描述即可生成复杂公式。", "mid", 40, 0.88, ["多维表格", "AI 公式"]),
    ev(12, 4, "other", "Keep 更新隐私政策", "更新了运动数据与健康数据的授权说明。", "low", 50, 0.55, ["隐私政策"]),
    ev(13, 5, "price_change", "Canva 推出 Pro 年付优惠", "年付方案最高可省 16%。", "mid", 45, 0.75, ["Canva Pro", "优惠"]),
    ev(14, 6, "new_feature", "Figma 推出 Dev Mode 增强", "开发者模式新增组件属性面板与代码片段导出。", "mid", 60, 0.86, ["Dev Mode", "Figma"]),
    ev(15, 8, "public_sentiment", "钉钉回应隐私相关讨论", "官方就近期隐私政策的疑问发布说明。", "low", 70, 0.62, ["隐私", "钉钉"]),
  ];

  // 报告：用模板生成一组周报/月报（字段与前端 ReportDetail 对齐）
  const mkReport = (id: number, type: any, title: string, rangeStart: string, rangeEnd: string, competitorsCount: number, favorite: boolean, weeksAgoCount: number) => {
    const typeLabel = type === "monthly" ? "月报" : "周报";
    const range = rangeStart === rangeEnd ? rangeStart : `${rangeStart} - ${rangeEnd}`;
    const generatedAt = rangeEnd;
    const [y, m] = rangeStart.split("-").slice(0, 2).map((s) => Number(s));
    const monthGroup = `${y}年${m}月`;
    return {
      id,
      type,
      typeLabel,
      title,
      range,
      rangeStart,
      rangeEnd,
      competitors: competitorsCount,
      favorite,
      generatedAt,
      monthGroup,
      deletedAt: null,
      summary: `本期共监控 ${competitorsCount} 个竞品，发现 24 个重要变化事件，涉及功能更新、价格调整、内容更新等多个方面。整体来看，AI 能力迭代仍是竞品竞争的主线，部分产品开始调整定价策略以应对市场变化。`,
      content: `# ${title}\n\n## 本周核心摘要\n\n本期共监控 ${competitorsCount} 个竞品，发现多个重要变化事件。AI 能力迭代仍是竞品竞争的主线。\n\n## 本期重点变化\n\n- **Notion**：推出全新 AI 功能套件，显著提升内容处理效率。\n- **飞书**：调整企业版定价策略，覆盖更多客户。\n\n## 建议关注\n\n建议重点跟进 AI 功能与定价变化对市场份额的后续影响。`,
      stats: [
        { key: "events", label: "重要变化事件", value: 24, delta: 12, deltaType: "up" },
        { key: "competitors", label: "涉及竞品", value: 7, delta: 8, deltaType: "up" },
        { key: "feature", label: "功能更新", value: 10, delta: 5, deltaType: "down" },
        { key: "price", label: "价格变化", value: 4, delta: 20, deltaType: "up" },
        { key: "impact", label: "高影响事件", value: 5, delta: 10, deltaType: "up" },
      ],
      highlights: [
        {
          id: id * 10 + 1,
          title: "Notion 推出全新 AI 功能套件",
          tag: "功能更新",
          tagType: "tag-feature",
          impact: "高影响",
          impactType: "high",
          points: ["Notion AI 新增智能总结、自动翻译、任务拆解等能力。", "推出 AI Agent，可自动执行跨页面任务流。"],
          affected: ["飞书", "Microsoft Loop", "Confluence"],
          foundAt: `${rangeStart} 10:24`,
          aiConfidence: 92,
        },
        {
          id: id * 10 + 2,
          title: "飞书调整企业版定价策略",
          tag: "价格变化",
          tagType: "tag-price",
          impact: "中影响",
          impactType: "mid",
          points: ["企业版基础版价格下调 15%。", "通过基础版降价 + 高级版增值覆盖更多客户。"],
          affected: ["钉钉", "企业微信"],
          foundAt: `${rangeStart} 09:15`,
          aiConfidence: 87,
        },
      ],
      categoryDist: [
        { name: "功能更新", value: 10 },
        { name: "价格变化", value: 4 },
        { name: "内容更新", value: 6 },
        { name: "舆论动态", value: 2 },
        { name: "其他", value: 2 },
      ],
      competitorRank: [
        { name: "Notion", value: 12 },
        { name: "飞书", value: 8 },
        { name: "钉钉", value: 6 },
        { name: "企业微信", value: 5 },
        { name: "Confluence", value: 4 },
      ],
      impactTrend: {
        dates: ["周一", "周二", "周三", "周四", "周五", "周六", "周日"],
        current: [3, 5, 8, 6, 7, 4, 5],
        previous: [2, 4, 5, 7, 5, 3, 4],
      },
      relatedEvents: [
        { id: 1, brand: "Notion", title: "Notion AI 新增智能总结等 5 项核心能力", tag: "功能更新", tagType: "tag-feature", time: `${rangeStart} 10:24` },
        { id: 2, brand: "飞书", title: "飞书企业版基础版价格下调 15%", tag: "价格变化", tagType: "tag-price", time: `${rangeStart} 09:15` },
      ],
      relatedCompetitors: [
        { name: "Notion", iconText: "N", iconBg: "#ececec", iconColor: "#222222", changes: 12 },
        { name: "飞书", iconText: "飞", iconBg: "#e6f4ff", iconColor: "#1890ff", changes: 8 },
        { name: "钉钉", iconText: "钉", iconBg: "#e6eaff", iconColor: "#5b6fff", changes: 6 },
      ],
      aiSteps: [
        { title: "数据采集", desc: "从官网、公告等数据源抓取竞品公开信息。", time: `${rangeEnd} 06:00` },
        { title: "事件识别", desc: "AI 识别出有效变化事件并完成去重分类。", time: `${rangeEnd} 06:12` },
        { title: "影响评估", desc: "对事件进行影响等级评估。", time: `${rangeEnd} 06:20` },
        { title: "报告生成", desc: "汇总生成竞品报告。", time: `${rangeEnd} 06:30` },
      ],
      shareToken: null,
      shareExpiresAt: null,
    };
  };

  const reports: any[] = [
    mkReport(1, "weekly", "2026年第25周 竞品周报", "2026-06-19", "2026-06-25", 12, true, 0),
    mkReport(2, "weekly", "2026年第24周 竞品周报", "2026-06-12", "2026-06-18", 12, false, 1),
    mkReport(3, "monthly", "2026年6月 竞品月报", "2026-06-01", "2026-06-30", 12, false, 0),
    mkReport(4, "weekly", "2026年第23周 竞品周报", "2026-05-29", "2026-06-04", 12, false, 2),
    mkReport(5, "weekly", "2026年第22周 竞品周报", "2026-05-22", "2026-05-28", 12, false, 3),
    mkReport(6, "weekly", "2026年第21周 竞品周报", "2026-05-15", "2026-05-21", 12, false, 4),
  ].map((r) => ({ ...r, userId: 1 }));

  // 抓取日志（几张示例）
  const crawlLogs: any[] = [
    { id: 1, competitorId: 3, competitorName: "ChatGPT", sourceId: null, sourceName: "定价页", sourceType: "pricing", url: "https://www.openai.com/pricing", trigger: "manual", status: "success", httpStatus: 200, changed: true, firstTime: false, eventCreated: true, durationMs: 1830, error: null, createdAt: hoursAgo(1) },
    { id: 2, competitorId: 1, competitorName: "Notion", sourceId: null, sourceName: "官网首页", sourceType: "homepage", url: "https://www.notion.so", trigger: "scheduler", status: "success", httpStatus: 200, changed: true, firstTime: false, eventCreated: true, durationMs: 1520, error: null, createdAt: hoursAgo(2) },
    { id: 3, competitorId: 5, competitorName: "Canva", sourceId: null, sourceName: "定价页", sourceType: "pricing", url: "https://www.canva.com/pricing", trigger: "manual", status: "failed", httpStatus: 504, changed: false, firstTime: false, eventCreated: false, durationMs: 30012, error: "渲染超时", createdAt: hoursAgo(8) },
  ].map((l) => ({ ...l, userId: 1 }));

  // LLM 供应商 / 配置（按用户隔离：admin 预置两条，demo no 数据）
  const providers: any[] = [
    { id: 1, userId: 1, name: "DeepSeek", baseUrl: "https://api.deepseek.com", model: "deepseek-chat", apiKey: "sk-mock", hasApiKey: true, isActive: true, sortOrder: 0, models: ["deepseek-chat", "deepseek-reasoner"] },
    { id: 2, userId: 1, name: "", baseUrl: "https://api.openai.com", model: "gpt-4o-mini", apiKey: "sk-mock", hasApiKey: true, isActive: false, sortOrder: 1, models: ["gpt-4o-mini", "gpt-4o"] },
  ];

  // ---- 普通用户（demo/demo1/demo2）各自独立的演示数据：竞品 + 事件 + 报告 + 抓取日志 ----
  // 与后端一致：竞品/报告/抓取日志带 user_id，事件通过竞品的 user_id 间接归属。
  let nextCompetitorId = 9;
  let nextEventId = 16;
  let nextReportId = 7;
  let nextCrawlLogId = 4;

  const addDemoCompetitor = (userId: number, name: string, host: string, cat: string) => {
    const id = nextCompetitorId++;
    const base = `https://www.${host}`;
    const row = {
      id,
      userId,
      name,
      officialUrl: base,
      category: cat,
      categoryType: cat === "设计工具" ? "tool" : "saas",
      status: "active",
      createdAt: daysAgo(20),
      deletedAt: null,
      restored: false,
      logoUrl: "",
      changes: 1 + (id % 5),
      todayChanges: id % 3,
      sources: [
        mkSource(id, "homepage", { url: base, lastCrawledAt: hoursAgo(id + 2) }),
        mkSource(id, "pricing", { url: `${base}/pricing`, lastCrawledAt: hoursAgo(id + 3) }),
      ],
    };
    competitors.push(row);
    events.push(
      {
        id: nextEventId++,
        competitorId: id,
        eventType: "new_feature",
        title: `${name} 上线新功能`,
        summary: `${name} 近期迭代发布了一项新能力，值得持续关注。`,
        aiAnalysis: null,
        keywords: [name],
        confidence: 0.9,
        priority: id % 2 === 0 ? "high" : "mid",
        createdAt: hoursAgo(id * 3),
        sourceName: "官网首页",
        diffDetail: null,
        sourceUrl: base,
      },
      {
        id: nextEventId++,
        competitorId: id,
        eventType: "content_update",
        title: `${name} 更新了产品文档`,
        summary: `${name} 更新了帮助中心与产品说明页内容。`,
        aiAnalysis: null,
        keywords: [name],
        confidence: 0.7,
        priority: "low",
        createdAt: hoursAgo(id * 8),
        sourceName: "官网首页",
        diffDetail: null,
        sourceUrl: base,
      },
    );
    return row;
  };

  const demoPlans: { userId: number; items: [string, string, string][] }[] = [
    { userId: 2, items: [["Linear", "linear.app", "开发者工具"], ["Loom", "loom.com", "SaaS工具"], ["Webflow", "webflow.com", "设计工具"]] },
    { userId: 3, items: [["Slack", "slack.com", "协作办公"], ["Miro", "miro.com", "协作办公"]] },
    { userId: 4, items: [["Zapier", "zapier.com", "开发者工具"], ["Airtable", "airtable.com", "协作办公"]] },
  ];

  for (const plan of demoPlans) {
    for (const [name, host, cat] of plan.items) {
      const cid = addDemoCompetitor(plan.userId, name, host, cat).id;
      if (name === plan.items[0][0]) {
        crawlLogs.push({
          id: nextCrawlLogId++,
          userId: plan.userId,
          competitorId: cid,
          competitorName: name,
          sourceId: null,
          sourceName: "官网首页",
          sourceType: "homepage",
          url: `https://www.${host}`,
          trigger: "scheduler",
          status: "success",
          httpStatus: 200,
          changed: true,
          firstTime: false,
          eventCreated: true,
          durationMs: 1200 + cid * 60,
          error: null,
          createdAt: hoursAgo(cid),
        });
      }
    }
    const rep = { ...mkReport(nextReportId++, "weekly", "2026年第25周 竞品周报", "2026-06-19", "2026-06-25", plan.items.length, false, 0), userId: plan.userId };
    reports.push(rep);
  }

  return {
    users,
    tokens: {},
    eventReads: [],
    competitors,
    events,
    reports,
    crawlLogs,
    providers,
    emailCodes: {},
    // 每个用户的 LLM 全局开关（只存 enabled/timeout/minChangeLines；凭证在 providers）。
    // 键为用户 id；未显式保存过的用户回退 env 默认（mock）。
    llmSetting: {
      1: { enabled: false, timeoutSeconds: 30, minChangeLines: 3, source: "env" },
      2: { enabled: false, timeoutSeconds: 30, minChangeLines: 3, source: "env" },
      3: { enabled: false, timeoutSeconds: 30, minChangeLines: 3, source: "env" },
      4: { enabled: false, timeoutSeconds: 30, minChangeLines: 3, source: "env" },
    },
    systemSettings: {
      smtp_host: "",
      smtp_port: 25,
      smtp_username: "",
      smtp_sender: "",
      smtp_password_set: false,
    },
    seq: { competitor: nextCompetitorId, event: nextEventId, report: nextReportId, crawlLog: nextCrawlLogId, provider: 3, source: sourceId, user: 5 },
  };
}

declare global {
  // eslint-disable-next-line no-var
  var __MOCK_DB__: DB | undefined;
}

export function db(): DB {
  if (!globalThis.__MOCK_DB__) globalThis.__MOCK_DB__ = createDB();
  return globalThis.__MOCK_DB__;
}

/** 当前用户名下的竞品 id 集合（事件/趋势/通知按竞品归属间接隔离） */
export function ownedCompetitorIds(userId: number, includeDeleted = false): Set<number> {
  return new Set(
    db()
      .competitors.filter((c) => (includeDeleted || !c.deletedAt) && c.userId === userId)
      .map((c) => c.id),
  );
}

// ---------- 序列化（把内部原始行转成前端期望的展示字段） ----------
const FAIL_THRESHOLD = 3;

export function serializeSource(s: any) {
  return {
    ...s,
    label: sourceLabel(s.sourceType),
    autoDisabled: !s.enabled && (s.failCount || 0) >= FAIL_THRESHOLD,
  };
}

function nextCrawlAt(sources: any[]): string {
  const enabled = sources.filter((s) => s.enabled);
  if (!enabled.length) return "已暂停";
  const nowMs = Date.now();
  const dues = enabled
    .filter((s) => s.lastCrawledAt)
    .map((s) => new Date(s.lastCrawledAt).getTime() + Math.max(1, s.intervalMinutes) * 60000);
  if (!dues.length) return "即将抓取";
  const earliest = Math.min(...dues);
  if (earliest <= nowMs) return "即将抓取";
  const d = new Date(earliest);
  const today = new Date();
  const delta = (new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime() -
    new Date(today.getFullYear(), today.getMonth(), today.getDate()).getTime()) / 86400000;
  if (delta === 0) return `今天 ${isoTime(d)}`;
  if (delta === 1) return `明天 ${isoTime(d)}`;
  return `${d.getMonth() + 1}月${d.getDate()}日 ${isoTime(d)}`;
}

/** 竞品原始行 → CompetitorItem */
export function serializeCompetitor(c: any) {
  const sources: any[] = (c.sources || []).map(serializeSource);
  const failed = sources.filter((s) => s.lastStatus === "failed");
  const enabled = c.status === "active";
  const fetched = sources.map((s) => s.lastCrawledAt).filter(Boolean).sort();
  const lastFetch = fetched[fetched.length - 1] ?? null;
  const intervals = sources.filter((s) => s.enabled).map((s) => s.intervalMinutes);

  let statusLabel = "已暂停";
  let statusType = "info";
  let statusDesc = "手动暂停";
  if (enabled) {
    statusLabel = failed.length ? "监控异常" : "监控中";
    statusType = failed.length ? "warning" : "success";
    statusDesc = failed.length ? `异常页面 ${failed.length} 个` : "正常";
  }

  return {
    id: c.id,
    name: c.name,
    domain: c.officialUrl || "",
    logoUrl: c.logoUrl || "",
    category: c.category || "SaaS工具",
    categoryType: c.categoryType || "saas",
    pages: sources.slice(0, 3).map((s) => s.name),
    extraPages: Math.max(0, sources.length - 3),
    frequency: intervals.length ? humanizeInterval(Math.min(...intervals)) : "未配置",
    frequencyDesc: sources.length ? "定时抓取" : "暂无监控源",
    lastFetchAgo: humanizeAgo(lastFetch),
    lastFetchTime: lastFetch ? formatDateTime(lastFetch) : "",
    nextCrawlAt: nextCrawlAt(sources),
    enabled,
    statusLabel,
    statusType,
    statusDesc,
    changes: c.changes ?? 0,
    todayChanges: c.todayChanges ?? 0,
    sources,
    deletedAt: c.deletedAt,
    restored: c.restored ?? false,
  };
}

/** 事件原始行 → EventRecord */
export function serializeEvent(e: any, competitor?: any) {
  const comp = competitor || { name: e.competitorName || "", officialUrl: "", logoUrl: "" };
  const meta = EVENT_TYPES[e.eventType] || EVENT_TYPES.other;
  const name = comp.name || "未知竞品";
  const createdAt = e.createdAt;
  const summary = e.summary || "";
  const tone = iconTone(name);

  return {
    id: e.id,
    competitorId: e.competitorId,
    competitorName: name,
    competitorDomain: comp.officialUrl || "",
    sourceName: e.sourceName || "未知页面",
    eventType: e.eventType,
    title: e.title,
    summary,
    aiAnalysis: e.aiAnalysis || null,
    keywords: e.keywords || [],
    confidence: e.confidence ?? 0,
    priorityLevel: e.priority,
    createdAt,
    date: isoDate(new Date(createdAt)),
    time: isoTime(new Date(createdAt)),
    dateLabel: dateLabel(createdAt),
    ago: humanizeAgo(createdAt),
    brand: name,
    brandDesc: e.sourceName || "",
    desc: summary.length <= 80 ? summary : summary.slice(0, 80) + "…",
    source: e.sourceName || "",
    domain: cleanHost(comp.officialUrl),
    logoUrl: comp.logoUrl || null,
    iconText: iconText(name),
    iconBg: tone[0],
    iconColor: tone[1],
    tag: meta.label,
    tagType: meta.tagType,
    category: meta.category,
    aiConfidence: Math.round((e.confidence ?? 0) * 100),
    priority: PRIORITY_LABELS[e.priority] || "中",
    priorityType: e.priority,
  };
}

export function serializeEventDetail(e: any, competitor?: any) {
  return {
    ...serializeEvent(e, competitor),
    url: competitor?.officialUrl || null,
    sourceUrl: e.sourceUrl || null,
    diffDetail: e.diffDetail || null,
  };
}

// ---------- 鉴权辅助（登录后其它接口从 Authorization 头还原当前用户） ----------

/** 从 token 反查用户行；查不到返回 null */
export function userFromToken(token: string): any | null {
  const d = db();
  const userId = token ? d.tokens[token] : undefined;
  if (!userId) return null;
  return d.users.find((u) => u.id === userId) ?? null;
}

/** 从响应上下文 headers 里解析出当前登录用户（无 token / token 无效返回 null） */
export function authUser(headers: any): any | null {
  const auth = (headers && (headers.authorization || headers.Authorization)) || "";
  const token = String(auth).replace(/^Bearer\s+/i, "").trim();
  return userFromToken(token);
}

/** 用户行 → 登录态里的 UserBrief（前端存下来渲染头像/昵称） */
export function userBrief(user: any) {
  return {
    id: user.id,
    name: user.name || user.username,
    username: user.username,
    avatar: user.avatar || "",
    email: user.email || "",
    is_admin: user.isAdmin,
  };
}

/** 用户行 → 用户中心资料（UserProfile，混合命名：passwordLength 驼峰 + is_admin 蛇形） */
export function userProfile(user: any) {
  return {
    id: user.id,
    username: user.username,
    nickname: user.name || "",
    email: user.email || "",
    avatar: user.avatar || "",
    passwordLength: user.password ? user.password.length : null,
    is_admin: user.isAdmin,
  };
}

/** 抹掉明文密码的用户行（用户管理列表项 AdminUser 用，snake_case） */
export function adminUser(user: any) {
  return {
    id: user.id,
    username: user.username,
    email: user.email || "",
    is_admin: user.isAdmin,
    is_active: user.active,
    password_length: user.password ? user.password.length : null,
  };
}

/** 新签发一个 token 并写入库 */
export function mintToken(userId: number): string {
  const d = db();
  const token = "mock-" + Math.random().toString(36).slice(2) + "-" + userId;
  d.tokens[token] = userId;
  return token;
}