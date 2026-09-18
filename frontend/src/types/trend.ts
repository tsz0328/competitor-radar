/**
 * 竞品情报趋势数据点
 * 供组件（TrendChart）、视图（Dashboard）、API 层共用
 */
export interface TrendPoint {
    date: string;
    feature: number; // 功能更新
    price: number; // 价格变动
    sentiment: number; // 舆论热度
    content: number; // 内容更新
    other: number; // 其他
}

/** 某个竞品的趋势洞察（由后端聚合事件 + AI 判断得出） */
export interface TrendInsight {
    competitorId: number;
    competitorName: string;
    periodDays: number;
    direction: "rising" | "stable" | "declining";
    /** 中文标签，如 活跃度上升 */
    directionLabel: string;
    summary: string;
    highlights: string[];
    eventCount: number;
    highImpactCount: number;
    coverageDays: number;
    generatedAt: string;
}

/** 工作台「近 N 天情报变化趋势」上的一个数据点 */
export interface DailyCount {
    /** 图表 x 轴，如 9/15 */
    date: string;
    /** 点击钻取用，如 2026-09-15 */
    dateIso: string;
    count: number;
}

/** 多竞品对比折线上的一个数据点（某天的变化总数） */
export interface CompetitorSeriesPoint {
    date: string;
    count: number;
}

/** 多竞品对比：某个竞品在一段时间内的每日变化总数 */
export interface CompetitorSeries {
    competitorId: number;
    competitorName: string;
    points: CompetitorSeriesPoint[];
}
