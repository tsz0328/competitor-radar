import request from "@/api/request";
import type { CrawlLogPage, CrawlLogQuery } from "@/types/crawlLog";

/** 抓取日志分页列表：按时间倒序，可按状态/触发方式/竞品过滤 */
export function fetchCrawlLogs(params: CrawlLogQuery): Promise<CrawlLogPage> {
  return request.get<unknown, CrawlLogPage>("/api/crawl-logs", { params });
}

/** 清空当前用户的全部抓取日志 */
export function clearCrawlLogs(): Promise<void> {
  return request.delete("/api/crawl-logs");
}
