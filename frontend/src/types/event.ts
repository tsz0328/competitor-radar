/**
 * 情报事件数据模型：供 API 层、stores、视图层共用
 */

/**
 * 单条情报事件（列表用）
 */
export interface EventRecord {
  id: number;
  /** 归属日期，如 2026-06-25 */
  date: string;
  /** 日期分组标签，如 今天 / 昨天 */
  dateLabel: string;
  /** 发生时间，如 10:24 */
  time: string;
  brand: string;
  brandDesc: string;
  domain: string;
  logoUrl?: string;
  iconText: string;
  iconBg: string;
  iconColor: string;
  /** 事件类型标签，如 价格变化 */
  tag: string;
  tagType: string;
  title: string;
  desc: string;
  /** AI 生成的完整说明（详情抽屉用；列表用的是其短版 desc） */
  summary?: string;
  /** AI 对该变化的推断/影响判断（与 summary 事实分离，仅代表模型观点） */
  aiAnalysis?: string | null;
  /** 归属竞品 id（右侧竞品筛选用） */
  competitorId?: number;
  /** 来源页面名，如 定价页 */
  source?: string;
  /** 竞品官网地址 */
  competitorDomain?: string;
  eventType?: string;
  /** 关键词标签 */
  keywords: string[];
  /** AI 置信度 0-100 */
  aiConfidence: number;
  /** 优先级：高 / 中 / 低 */
  priority: string;
  priorityType: "high" | "mid" | "low";
  /** 相对时间，如 2 小时前 */
  ago: string;
  /** 统计分类，与 EventSummary 的键对齐（不含 total） */
  category: "feature" | "price" | "content" | "negative" | "other";
}

/**
 * 通知中心一条：事件记录 + 服务端已读态（多端一致）
 */
export interface NotificationRecord extends EventRecord {
  isRead: boolean;
}

/**
 * 事件流页面：顶部类型统计
 */
export interface EventSummary {
  total: number;
  feature: number;
  price: number;
  content: number;
  negative: number;
  other: number;
  /** 优先级分面计数（不被优先级自身筛选清零） */
  high: number;
  mid: number;
  low: number;
}

export interface EventListResult {
  summary: EventSummary;
  total: number;
  records: EventRecord[];
}

/** 一条历史快照（详情抽屉「查看历史快照」用） */
export interface EventSnapshot {
  id: number;
  crawledAt: string;
  /** 格式化后的抓取时间，如 2026-09-18 08:21 */
  crawledAtLabel: string;
  /** 是否留了可查看的原始 HTML */
  available: boolean;
  /** 这次抓取是否检测到变化 */
  changeDetected: boolean;
  /** 是否为该事件自身对应的那次抓取 */
  isCurrent: boolean;
}

/**
 * 工作台「AI 今日洞察」：统计数字来自后端聚合，summary/highlights 来自 LLM（无 Key 时规则兜底）
 */
export interface DailyInsight {
  days: number;
  /** 中文时间范围，如「过去 24 小时」 */
  periodText: string;
  eventCount: number;
  highCount: number;
  competitorCount: number;
  summary: string;
  highlights: string[];
  /** 是否来自真实模型（false = 规则 Mock） */
  fromLlm: boolean;
  generatedAt: string;
}

/** 事件详情：在列表字段之外补上差异原文与相关地址 */
export interface EventDetail extends EventRecord {
  /** 竞品官网 */
  url?: string | null;
  /** 真正发生变化的那张页面 */
  sourceUrl?: string | null;
  /** difflib 差异原文（unified diff） */
  diffDetail?: string | null;
  /** AI 对该变化的推断/影响判断（与 summary 事实分离，仅代表模型观点） */
  aiAnalysis?: string | null;
  createdAt?: string;
}
