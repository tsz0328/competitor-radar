import request, { LONG_REQUEST_TIMEOUT } from "@/api/request";
import type {
  CompetitorCreatePayload,
  CompetitorItem,
  CompetitorUpdatePayload,
  CrawlResult,
  DiscoverResult,
  SourceTypeOption,
  SuggestResult,
} from "@/types/competitor";

/** 「校验网址可达」接口的返回：ok=是否可访问，message=给人看的结论 */
export interface UrlCheckResult {
  url: string;
  ok: boolean;
  httpStatus: number | null;
  message: string;
}

/** 保存竞品前探一下某个网址是否可达（后端发一次短超时 GET，不落库） */
export function checkSourceUrl(
  url: string,
  signal?: AbortSignal,
): Promise<UrlCheckResult> {
  return request.post<unknown, UrlCheckResult>(
    "/api/competitors/check-url",
    { url },
    { signal },
  );
}

/**
 * 自动寻找监控页：后端读官网首页的链接，猜出定价页/更新日志/博客/文档/状态页/RSS
 * 的地址并校验可达。多个页面探测耗时较长，放宽超时。
 */
export function discoverSources(
  officialUrl: string,
  skipTypes: string[] = [],
  signal?: AbortSignal,
): Promise<DiscoverResult> {
  return request.post<unknown, DiscoverResult>(
    "/api/competitors/discover-sources",
    { officialUrl, skipTypes },
    { timeout: LONG_REQUEST_TIMEOUT, signal },
  );
}

/**
 * 智能预填：根据竞品名称推断官网地址与分类。
 * - useLlm=true（默认）：调 AI 推断（「智能检测填充」按钮用）；
 * - useLlm=false：只用规则域名探测，不消耗 AI（用户自己填竞品时的自动预填用）。
 * 可能触发多个域名的探活，放宽超时。
 */
export function suggestCompetitor(
  name: string,
  categories: string[] = [],
  useLlm = true,
  signal?: AbortSignal,
): Promise<SuggestResult> {
  return request.post<unknown, SuggestResult>(
    "/api/competitors/suggest",
    { name, categories, useLlm },
    { timeout: LONG_REQUEST_TIMEOUT, signal },
  );
}

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



/**
 * 立即抓取该竞品下所有启用的监控页面。
 *
 * 单次抓取包含：启动浏览器内核 + 逐页渲染 + LLM 分析，耗时远超普通接口，
 * 因此单独放宽超时，避免被全局 10s 误杀（表现为 "timeout of 10000ms exceeded"）。
 */
export function crawlCompetitor(id: number): Promise<CrawlResult> {
  return request.post<unknown, CrawlResult>(
    `/api/competitors/${id}/crawl`,
    undefined,
    { timeout: LONG_REQUEST_TIMEOUT },
  );
}

/** 删除竞品监控配置：移入回收站（软删除），30 天内可在「回收站」恢复；后端 204 无响应体 */
export function deleteCompetitor(id: number): Promise<void> {
  return request.delete<unknown, void>(`/api/competitors/${id}`);
}

/** 回收站列表：当前用户已软删除、尚在保留期内的竞品 */
export function fetchTrash(): Promise<CompetitorItem[]> {
  return request.get<unknown, CompetitorItem[]>("/api/competitors/trash");
}

/** 从回收站恢复竞品：清除删除标记，历史数据重新可用 */
export function restoreCompetitor(id: number): Promise<CompetitorItem> {
  return request.post<unknown, CompetitorItem>(`/api/competitors/trash/${id}`);
}

/** 从回收站彻底删除竞品：连事件与快照一并清除，不可恢复；后端 204 无响应体 */
export function purgeCompetitor(id: number): Promise<void> {
  return request.delete<unknown, void>(`/api/competitors/trash/${id}`);
}

/** 一键重新启用被「连续失败自动停用」的监控源，并清零失败计数 */

export function reviveSources(id: number): Promise<CompetitorItem> {
  return request.post<unknown, CompetitorItem>(
    `/api/competitors/${id}/revive-sources`,
  );
}

/** 拉取可选的监控页面类型（来自后端注册表，前后端口径唯一） */
export function fetchSourceTypes(): Promise<SourceTypeOption[]> {
  return request.get<unknown, SourceTypeOption[]>("/api/source-types");
}

const faviconCache = new Map<string, Promise<{ logoUrl: string | null }>>();

/**
 * 解析竞品域名的真实图标地址（后端读首页 <link rel="icon">）。
 * 用于 SPA 站点兜底：其 /favicon.ico 会被返回成 HTML，前端直连探测必然失败。
 *
 * 按 domain 缓存 Promise：同一域名并发/重复调用只发一次后端请求，
 * 避免工作台多个事件卡片渲染同一品牌时刷屏 `/competitors/favicon`。
 */
export function resolveFavicon(
  domain: string,
): Promise<{ logoUrl: string | null }> {
  if (!domain) return Promise.resolve({ logoUrl: null });
  if (!faviconCache.has(domain)) {
    faviconCache.set(
      domain,
      request.get<unknown, { logoUrl: string | null }>(
        "/api/competitors/favicon",
        { params: { domain } },
      ),
    );
  }
  return faviconCache.get(domain)!;
}
