/**
 * 竞品情报事件数据模型
 * 供 API 层、stores、视图层共用
 */
export interface EventItem {
  time: string;
  brand: string;
  domain: string;
  logoUrl?: string;
  iconText: string;
  iconBg: string;
  iconColor: string;
  title: string;
  tag: string;
  tagType: string;
  desc: string;
  source: string;
}

/**
 * 事件流页面：单条情报事件
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
 * 事件流页面：顶部类型统计
 */
export interface EventSummary {
  total: number;
  feature: number;
  price: number;
  content: number;
  negative: number;
  other: number;
}

export interface EventListResult {
  summary: EventSummary;
  records: EventRecord[];
}
