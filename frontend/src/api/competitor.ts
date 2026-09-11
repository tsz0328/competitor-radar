import request from "@/api/request";
import type {
  CompetitorCreatePayload,
  CompetitorItem,
  CompetitorUpdatePayload,
  CrawlResult,
  SourceTypeOption,
} from "@/types/competitor";

export function fetchCompetitors(): Promise<CompetitorItem[]> {
  return request.get<unknown, CompetitorItem[]>("/api/competitors");
}

/** 新增竞品（连同要监控的页面） */
export function createCompetitor(
  payload: CompetitorCreatePayload,
): Promise<CompetitorItem> {
  return request.post<unknown, CompetitorItem>("/api/competitors", payload);
}

/** 编辑竞品：sources 传了即整份对齐监控源 */
export function updateCompetitor(
  id: number,
  payload: CompetitorUpdatePayload,
): Promise<CompetitorItem> {
  return request.patch<unknown, CompetitorItem>(`/api/competitors/${id}`, payload);
}

/** 删除竞品（连同其监控源，后端 204 无响应体） */
export function deleteCompetitor(id: number): Promise<void> {
  return request.delete<unknown, void>(`/api/competitors/${id}`);
}

/** 立即抓取该竞品下所有启用的监控页面 */
export function crawlCompetitor(id: number): Promise<CrawlResult> {
  return request.post<unknown, CrawlResult>(`/api/competitors/${id}/crawl`);
}

/** 拉取可选的监控页面类型（来自后端注册表，前后端口径唯一） */
export function fetchSourceTypes(): Promise<SourceTypeOption[]> {
  return request.get<unknown, SourceTypeOption[]>("/api/source-types");
}
