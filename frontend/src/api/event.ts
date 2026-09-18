import request, { LONG_REQUEST_TIMEOUT } from "@/api/request";
import type {
  DailyInsight,
  EventDetail,
  EventListResult,
  EventRecord,
  EventSnapshot,
} from "@/types/event";

/** 事件列表：顶部统计 + 事件记录（事件流页与 Dashboard 共用） */
export function fetchEventList(params?: Record<string, unknown>): Promise<EventListResult> {
  return request.get<unknown, EventListResult>("/api/events", { params });
}

/** 工作台「AI 今日洞察」：聚合近 N 天事件后由 AI 总结，需等 LLM，故放宽超时 */
export function fetchDailyInsight(days = 1): Promise<DailyInsight> {
  return request.get<unknown, DailyInsight>("/api/events/daily-insight", {
    params: { days },
    timeout: LONG_REQUEST_TIMEOUT,
  });
}

/** 事件详情：含触发本次事件的差异原文 */
export function fetchEventDetail(id: number): Promise<EventDetail> {
  return request.get<unknown, EventDetail>(`/api/events/${id}`);
}

/** 该事件所属监控页面的历史快照（详情抽屉「查看历史快照」用） */
export function fetchEventSnapshots(
  eventId: number,
  limit = 10,
): Promise<EventSnapshot[]> {
  return request.get<unknown, EventSnapshot[]>(`/api/events/${eventId}/snapshots`, {
    params: { limit },
  });
}

/** 某条快照抓取时的原始 HTML（在 sandbox iframe 内查看，不执行脚本） */
export function fetchSnapshotRaw(snapshotId: number): Promise<string> {
  return request.get<unknown, string>(`/api/snapshots/${snapshotId}/raw`, {
    responseType: "text",
  });
}

/** 相关事件：同竞品其它近期事件（详情抽屉"相关事件"用） */
export function fetchRelatedEvents(params: {
  competitorId: number;
  excludeId?: number;
  limit?: number;
  /** 仅取最近 N 天内的事件 */
  days?: number;
  /** 按分类筛选：feature/price/content/negative/other */
  category?: string;
}): Promise<EventRecord[]> {
  return request.get<unknown, EventRecord[]>("/api/events/related", { params });
}
