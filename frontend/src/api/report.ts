import request, { LONG_REQUEST_TIMEOUT } from "@/api/request";
import type { ReportDetail, ReportListResult } from "@/types/report";

/** 周报列表 */
export function fetchReportList(): Promise<ReportListResult> {
  return request.get<unknown, ReportListResult>("/api/reports");
}

/** 周报详情 */
export function fetchReportDetail(id: number): Promise<ReportDetail> {
  return request.get<unknown, ReportDetail>(`/api/reports/${id}`);
}

/** 切换收藏（收藏存在账号下，换浏览器/换设备都在） */
export function setReportFavorite(
  id: number,
  favorite: boolean,
): Promise<ReportDetail> {
  return request.patch<unknown, ReportDetail>(`/api/reports/${id}/favorite`, {
    favorite,
  });
}

/** 手动生成一份周报（整份由 LLM 生成，耗时长，单独放宽超时） */
export function generateReport(weeksAgo = 0): Promise<ReportDetail> {
  return request.post<unknown, ReportDetail>("/api/reports/generate", null, {
    params: { weeksAgo },
    timeout: LONG_REQUEST_TIMEOUT,
  });
}
