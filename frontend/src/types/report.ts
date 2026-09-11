/**
 * AI 竞品报告数据模型
 * 供 API 层、stores、视图层共用
 */

/** 报告列表项（左侧列表） */
export interface ReportListItem {
  id: number;
  /** 报告标题，如 2026年第25周 竞品周报 */
  title: string;
  /** 报告类型 */
  type: "weekly" | "monthly";
  /** 类型标签，如 周报 / 月报 */
  typeLabel: string;
  /** 覆盖周期，如 6月19日 - 6月25日 */
  range: string;
  /** 监控竞品数量 */
  competitors: number;
  /** 生成日期，如 2026-06-25 */
  generatedAt: string;
  /** 是否收藏 */
  favorite: boolean;
  /** 月份分组，如 2026年6月 */
  monthGroup: string;
}

export interface ReportListResult {
  /** 报告总数（含未展示的历史报告） */
  total: number;
  reports: ReportListItem[];
}

/** 核心摘要统计项 */
export interface ReportStatItem {
  /** 与前端展示配置对齐的键 */
  key: "events" | "competitors" | "feature" | "price" | "impact";
  label: string;
  value: number;
  /** 环比数值（百分数，不带符号），如 27 */
  delta: number;
  /** 环比方向 */
  deltaType: "up" | "down";
}

/** 本周重点变化条目 */
export interface ReportHighlight {
  id: number;
  title: string;
  /** 事件类型标签，如 功能更新 */
  tag: string;
  /** 标签样式类，如 tag-feature */
  tagType: string;
  /** 影响等级，如 高影响 */
  impact: string;
  impactType: "high" | "mid";
  /** 要点列表 */
  points: string[];
  /** 受影响竞品 */
  affected: string[];
  /** 发现时间，如 2026-06-20 10:24 */
  foundAt: string;
  /** AI 置信度 0-100 */
  aiConfidence: number;
}

/** 通用 名称-数值 对（图表用） */
export interface NameValue {
  name: string;
  value: number;
}

/** 高影响事件趋势（本周 vs 上周） */
export interface ImpactTrend {
  dates: string[];
  current: number[];
  previous: number[];
}

/** 相关事件（报告关联的情报事件） */
export interface ReportRelatedEvent {
  id: number;
  brand: string;
  title: string;
  tag: string;
  tagType: string;
  /** 发现时间，如 2026-06-20 10:24 */
  time: string;
}

/** 涉及竞品 */
export interface ReportRelatedCompetitor {
  name: string;
  iconText: string;
  iconBg: string;
  iconColor: string;
  /** 本期变化数量 */
  changes: number;
}

/** AI 分析过程步骤 */
export interface ReportAiStep {
  title: string;
  desc: string;
  time: string;
}

/** 报告详情 */
export interface ReportDetail {
  id: number;
  title: string;
  typeLabel: string;
  rangeStart: string;
  rangeEnd: string;
  competitors: number;
  favorite: boolean;
  /** 本周核心摘要 */
  summary: string;
  stats: ReportStatItem[];
  highlights: ReportHighlight[];
  /** 事件类型分布 */
  categoryDist: NameValue[];
  /** 竞品活跃度 TOP5 */
  competitorRank: NameValue[];
  /** 高影响事件趋势 */
  impactTrend: ImpactTrend;
  relatedEvents: ReportRelatedEvent[];
  relatedCompetitors: ReportRelatedCompetitor[];
  aiSteps: ReportAiStep[];
}
