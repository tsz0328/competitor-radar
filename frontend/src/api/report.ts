import request, { LONG_REQUEST_TIMEOUT } from "@/api/request";
import type { ReportDetail, ReportListItem, ReportListResult } from "@/types/report";

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

/** 生成接口结果：每次调用都直接新建一份新的报告 */
export interface ReportGenerateResult {
  status: "created";
  report?: ReportDetail | null;
}

/**
 * 手动生成一份报告（整份由 LLM 生成，耗时长，单独放宽超时）。
 * 每次生成都是新的一份，可重复生成、互不覆盖。
 * @param reportType weekly=周报（周一到今天）/ monthly=月报（本月1号到今天）
 */
export function generateReport(
  reportType: "weekly" | "monthly" = "weekly",
): Promise<ReportGenerateResult> {
  return request.post<unknown, ReportGenerateResult>(
    "/api/reports/generate",
    null,
    {
      params: { reportType },
      timeout: LONG_REQUEST_TIMEOUT,
    },
  );
}

/** 删除一份周报/月报：移入回收站（保留期内可恢复） */
export function deleteReport(id: number): Promise<{ ok: boolean }> {
  return request.delete<unknown, { ok: boolean }>(`/api/reports/${id}`);
}

/** 回收站列表：已删除、尚在保留期内的周报/月报 */
export function fetchTrashReports(): Promise<ReportListItem[]> {
  return request.get<unknown, ReportListItem[]>("/api/reports/trash");
}

/** 从回收站恢复一份周报/月报 */
export function restoreReport(id: number): Promise<ReportListItem> {
  return request.post<unknown, ReportListItem>(`/api/reports/trash/${id}`);
}

/** 从回收站彻底删除一份周报/月报（不可恢复） */
export function purgeReport(id: number): Promise<void> {
  return request.delete<unknown, void>(`/api/reports/trash/${id}`);
}

/** 可导出的文件格式 */
export type ReportExportFormat = "pdf" | "md" | "html" | "docx";

/**
 * 导出周报为可打印 HTML 文本（format=pdf）。
 * 打印页是独立文档、需带 Authorization，直接用 window.open 会因无 token 触发 401，
 * 故走已鉴权请求拉取文本，再由调用方写入新窗口触发打印 / 另存 PDF。
 */
export function exportReportPdf(id: number): Promise<string> {
  return request.get<unknown, string>(`/api/reports/${id}/export`, {
    params: { format: "pdf" },
    responseType: "text",
  });
}

/** 导出周报为文本文件内容（Markdown / HTML），由调用方包装成 Blob 下载 */
export function exportReportText(
  id: number,
  format: Extract<ReportExportFormat, "md" | "html">,
): Promise<string> {
  return request.get<unknown, string>(`/api/reports/${id}/export`, {
    params: { format },
    responseType: "text",
  });
}

/** 导出周报为 Word 文档（二进制），直接得到 Blob 供下载 */
export function exportReportDocx(id: number): Promise<Blob> {
  return request.get<unknown, Blob>(`/api/reports/${id}/export`, {
    params: { format: "docx" },
    responseType: "blob",
  });
}

/** 免登录分享链接的响应（token；前端拼完整 URL 供复制） */
export interface ReportShareResult {
  token: string;
  expiresAt: string; // ISO；空 = 永久有效
}

/**
 * 生成/重置周报的免登录分享链接。
 * @param expiresDays 有效期（天）；传 null 表示永久有效
 */
export function createReportShare(
  id: number,
  expiresDays: number | null,
): Promise<ReportShareResult> {
  return request.post<unknown, ReportShareResult>(`/api/reports/${id}/share`, {
    expiresDays,
  });
}

/** 查询周报当前有效的免登录分享；无分享或已过期返回 null */
export function fetchReportShare(id: number): Promise<ReportShareResult | null> {
  return request.get<unknown, ReportShareResult | null>(`/api/reports/${id}/share`);
}

/** 撤销周报的免登录分享链接 */
export function revokeReportShare(id: number): Promise<{ ok: boolean }> {
  return request.delete<unknown, { ok: boolean }>(`/api/reports/${id}/share`);
}
