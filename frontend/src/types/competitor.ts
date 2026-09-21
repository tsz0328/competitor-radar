/**
 * 竞品监控列表数据模型
 * 供 API 层、stores、视图层共用
 */
export interface CompetitorItem {
  id: number;
  name: string;
  domain: string;
  logoUrl?: string;
  /** 分类标签，如 SaaS工具 / AI产品 */
  category: string;
  /** 分类标签样式类型（v1 只监控同类 SaaS / App，不含电商） */
  categoryType: "saas" | "ai" | "app" | "tool";
  /** 监控页面名称列表 */
  pages: string[];
  /** 折叠的额外页面数量 */
  extraPages: number;
  /** 监控频率，如 每天 */
  frequency: string;
  frequencyDesc: string;
  /** 最近抓取相对时间，如 2 小时前 */
  lastFetchAgo: string;
  /** 最近抓取绝对时间 */
  lastFetchTime: string;
  /** 预计下次抓取时间，如「明天 08:00」/「即将抓取」/「已暂停」 */
  nextCrawlAt: string;
  /** 监控开关：true=开启，false=暂停 */
  enabled: boolean;
  /** 展示用中文状态：监控中 / 已暂停 */
  statusLabel: string;
  statusType: "success" | "warning" | "info";
  statusDesc: string;
  /** 最近变化条数 */
  changes: number;
  /** 今日新增变化 */
  todayChanges: number;
  /** 该竞品下的监控源（详情/编辑用） */
  sources?: MonitorSourceItem[];
  /** 软删除标记：非空表示已移入回收站（ISO 时间字符串） */
  deletedAt?: string | null;
  /** 新增竞品时若命中回收站里的同竞品并恢复，则为 true */
  restored?: boolean;
}

/** v1 支持的数据源类型（与后端 SOURCE_TYPE_REGISTRY 对齐） */
export type SourceType =
  | "homepage"
  | "pricing"
  | "changelog"
  | "blog"
  | "docs"
  | "status"
  | "rss"
  | "app_store";

/** 后端返回的"可选监控页面"目录项 */
export interface SourceTypeOption {
  type: SourceType;
  label: string;
  render: "browser" | "http";
  defaultIntervalMinutes: number;
  llmHint: string;
}

/** 新增竞品时提交的单个监控源 */
export interface MonitorSourceInput {
  sourceType: SourceType;
  url?: string;
  name?: string;
  intervalMinutes?: number;
}

/** 后端返回的监控源实体 */
export interface MonitorSourceItem {
  id: number;
  competitorId: number;
  sourceType: SourceType;
  label: string;
  name: string;
  url: string;
  renderMode: "browser" | "http";
  intervalMinutes: number;
  enabled: boolean;
  lastStatus?: string | null;
  lastError?: string | null;
  failCount?: number;
  lastCrawledAt?: string | null;
  /** 是否被「连续失败自动停用」：前端据此展示提示与重新启用按钮 */
  autoDisabled?: boolean;
}

/** 单个监控源的抓取结果 */
export interface CrawlSourceResult {
  sourceId: number;
  sourceName: string;
  sourceType: SourceType;
  status: "success" | "failed" | "skipped";
  httpStatus?: number | null;
  /** 相比上次基准是否发生变化 */
  changed: boolean;
  /** 是否本次才首次抓取（建立基准，不算变化） */
  firstTime: boolean;
  /** 本次抓取是否因此产出了一条情报事件（变化且通过显著性过滤） */
  eventCreated: boolean;
  error?: string | null;
  durationMs: number;
}

/** 一次「立即抓取」的汇总结果 */
export interface CrawlResult {
  competitorId: number;
  total: number;
  succeeded: number;
  failed: number;
  changed: number;
  results: CrawlSourceResult[];
}

/** 新增竞品的请求体 */
export interface CompetitorCreatePayload {
  name: string;
  officialUrl: string;
  category?: string;
  sources?: MonitorSourceInput[];
}

/** 编辑竞品的请求体（PATCH，语义为局部更新，字段均可选） */
export type CompetitorUpdatePayload = Partial<CompetitorCreatePayload> & {
  /** 监控开关：active=开启监控，paused=暂停监控 */
  status?: "active" | "paused";
};

/** 自动发现：单个监控页类型的查找结果 */
export interface DiscoveredSource {
  sourceType: SourceType;
  label: string;
  /** 找到时为地址，未找到为 null */
  url: string | null;
  found: boolean;
  /** 来源：link=首页链接 / sitemap / common=常见路径兜底 */
  origin: string;
  httpStatus?: number | null;
}

/** 自动发现：一次「自动寻找页面」的整体结果 */
export interface DiscoverResult {
  officialUrl: string;
  /** 官网首页是否可达（不可达时无法自动发现） */
  homepageReachable: boolean;
  sources: DiscoveredSource[];
}

/** 智能预填：根据竞品名称推断的官网地址与分类 */
export interface SuggestResult {
  officialUrl: string | null;
  category: string | null;
  /** llm=AI 推断 / probe=域名探测 / none=没识别出来 */
  source: string;
  message: string;
}
