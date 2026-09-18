import request, { LONG_REQUEST_TIMEOUT } from "@/api/request";
import type { CompetitorSeries, DailyCount, TrendInsight, TrendPoint } from "@/types/trend";

/** 全部竞品汇总的每日变化总数（工作台趋势图，点某天可钻取到情报中心） */
export function fetchDailyTrend(days: 7 | 30 | 90 = 30): Promise<DailyCount[]> {
  return request.get<unknown, DailyCount[]>("/api/trends/daily", {
    params: { days },
  });
}

/** 全部竞品汇总的趋势序列（Dashboard 的「竞品动态趋势」用） */
export function fetchTrend(days: 7 | 30 | 90): Promise<TrendPoint[]> {
  return request.get<unknown, TrendPoint[]>("/api/trends/overview", {
    params: { days },
  });
}

/** 多竞品变化对比：每个竞品各自的每日变化总数序列 */
export function fetchTrendCompare(
  days: 7 | 30 | 90,
): Promise<CompetitorSeries[]> {
  return request.get<unknown, CompetitorSeries[]>("/api/trends/compare", {
    params: { days },
  });
}

/** 某个竞品的变化趋势序列 */
export function fetchCompetitorTrend(
  competitorId: number,
  days: 7 | 30 | 90 = 30,
): Promise<TrendPoint[]> {
  return request.get<unknown, TrendPoint[]>(`/api/trends/${competitorId}/chart`, {
    params: { days },
  });
}

/** 某个竞品的趋势洞察（没有或过期时后端会自动生成一次，需等 LLM，故放宽超时） */
export function fetchTrendInsight(
  competitorId: number,
  periodDays?: number,
): Promise<TrendInsight> {
  return request.get<unknown, TrendInsight>(`/api/trends/${competitorId}`, {
    params: periodDays ? { periodDays } : undefined,
    timeout: LONG_REQUEST_TIMEOUT,
  });
}
