import request from "@/api/request";
import type { EventDetail, EventItem, EventListResult } from "@/types/event";

/** Dashboard 的「最新事件」：取列表前几条即可 */
export function fetchEvents(): Promise<EventItem[]> {
  return request
    .get<unknown, EventListResult>("/api/events", { params: { limit: 6 } })
    .then((result) =>
      result.records.map((record) => ({
        time: record.time,
        brand: record.brand,
        domain: record.domain,
        logoUrl: record.logoUrl,
        iconText: record.iconText,
        iconBg: record.iconBg,
        iconColor: record.iconColor,
        title: record.title,
        tag: record.tag,
        tagType: record.tagType,
        desc: record.desc,
        source: record.source ?? record.brandDesc,
      })),
    );
}

/** 事件流页面：顶部统计 + 事件记录 */
export function fetchEventList(): Promise<EventListResult> {
  return request.get<unknown, EventListResult>("/api/events");
}

/** 事件详情：含触发本次事件的差异原文 */
export function fetchEventDetail(id: number): Promise<EventDetail> {
  return request.get<unknown, EventDetail>(`/api/events/${id}`);
}
