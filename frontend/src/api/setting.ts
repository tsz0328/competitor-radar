import request from "@/api/request";

/** 当前 AI 模型配置（Key 已脱敏，不含明文） */
export interface LlmSetting {
  enabled: boolean;
  hasApiKey: boolean;
  /** 脱敏预览，如 sk-****abcd */
  apiKeyPreview: string;
  baseUrl: string;
  model: string;
  timeoutSeconds: number;
  minChangeLines: number;
  /** real = 走真实模型；mock = 规则兜底 */
  mode: "real" | "mock";
  /** database = 已在设置页保存；env = 读的是 .env 默认值 */
  source: "database" | "env";
  message: string;
}

/** 保存设置的入参（只提交要改的字段） */
export interface LlmSettingUpdate {
  enabled?: boolean;
  /** 留空表示不修改；有值则覆盖 */
  apiKey?: string;
  /** true 时无条件清除已保存的 Key */
  clearApiKey?: boolean;
  baseUrl?: string;
  model?: string;
  timeoutSeconds?: number;
  minChangeLines?: number;
}

export interface LlmTestRequest {
  /** 测试已保存的供应商时传入：它的 Key 前端拿不到（脱敏），由后端自己取 */
  providerId?: number;
  baseUrl?: string;
  model?: string;
  apiKey?: string;
  timeoutSeconds?: number;
}

export interface LlmTestResult {
  ok: boolean;
  message: string;
  model: string;
  latencyMs: number;
}

/** 读取当前 AI 模型配置 */
export function fetchLlmSetting(): Promise<LlmSetting> {
  return request.get<unknown, LlmSetting>("/api/settings/llm");
}

/** 保存 AI 模型配置（保存后立即生效） */
export function updateLlmSetting(payload: LlmSettingUpdate): Promise<LlmSetting> {
  return request.put<unknown, LlmSetting>("/api/settings/llm", payload);
}

/**
 * 测试模型连通性。
 *
 * 后端按 timeoutSeconds 等待模型返回，前端必须比它更晚超时，否则模型还没回、
 * 前端就先报 "timeout of 10000ms exceeded"。这里取请求里的 timeoutSeconds + 5s 缓冲。
 */
export function testLlmSetting(payload: LlmTestRequest): Promise<LlmTestResult> {
  const waitMs = ((payload.timeoutSeconds ?? 30) + 5) * 1000;
  return request.post<unknown, LlmTestResult>(
    "/api/settings/llm/test",
    payload,
    { timeout: waitMs },
  );
}

/** 已配置的模型供应商（Key 已脱敏，不含明文） */
export interface LlmProvider {
  id: number;
  /** 展示名，如 DeepSeek；空串表示未命名（界面显示「自定义」） */
  name: string;
  baseUrl: string;
  model: string;
  hasApiKey: boolean;
  apiKeyPreview: string;
  /** 运行时正在使用这一条 */
  isActive: boolean;
  /** 已缓存的模型数量；完整列表用 fetchLlmProviderModels 按需取 */
  modelsCount: number;
}

/** 添加供应商的入参 */
export interface LlmProviderCreatePayload {
  name?: string;
  baseUrl: string;
  model: string;
  apiKey: string;
  /** 添加前已从上游拉到的模型列表（可选） */
  models?: string[];
}

/** 编辑供应商的入参（只提交要改的字段） */
export interface LlmProviderUpdatePayload {
  name?: string;
  baseUrl?: string;
  model?: string;
  /** 留空表示不修改；有值则覆盖 */
  apiKey?: string;
  clearApiKey?: boolean;
  /** 省略 = 保持不变；传了就覆盖（保存本次新拉到的模型列表） */
  models?: string[];
}

/** 已配置的供应商列表（使用中的排最前） */
export function fetchLlmProviders(): Promise<LlmProvider[]> {
  return request.get<unknown, LlmProvider[]>("/api/settings/llm/providers");
}

/** 添加供应商（第一条自动设为「使用中」并立即生效） */
export function createLlmProvider(payload: LlmProviderCreatePayload): Promise<LlmProvider> {
  return request.post<unknown, LlmProvider>("/api/settings/llm/providers", payload);
}

/** 编辑供应商（只改传了的字段） */
export function updateLlmProvider(
  id: number,
  payload: LlmProviderUpdatePayload,
): Promise<LlmProvider> {
  return request.put<unknown, LlmProvider>(`/api/settings/llm/providers/${id}`, payload);
}

/** 删除供应商；删的是「使用中」的则自动切换到最新一条 */
export function deleteLlmProvider(id: number): Promise<void> {
  return request.delete(`/api/settings/llm/providers/${id}`);
}

/** 拖动排序：按期望顺序传一组供应商 id（仅改展示顺序） */
export function reorderLlmProviders(ids: number[]): Promise<void> {
  return request.post<unknown, void>("/api/settings/llm/providers/reorder", { ids });
}

/** 切换「使用中」的供应商，运行时立即改用它的配置 */
export function activateLlmProvider(id: number): Promise<LlmProvider> {
  return request.post<unknown, LlmProvider>(`/api/settings/llm/providers/${id}/activate`);
}

/** 复制供应商（含已保存的 Key），副本追加到末尾且不设为「使用中」 */
export function duplicateLlmProvider(id: number): Promise<LlmProvider> {
  return request.post<unknown, LlmProvider>(`/api/settings/llm/providers/${id}/duplicate`);
}

/** 读取某条已保存供应商的 API Key 明文（编辑弹窗回显用；列表只给脱敏值） */
export function fetchLlmProviderApiKey(id: number): Promise<string> {
  return request
    .get<unknown, { apiKey: string }>(`/api/settings/llm/providers/${id}/api-key`)
    .then((res) => res.apiKey || "");
}

/** 从上游供应商拉取模型列表的入参 */
export interface LlmFetchModelsRequest {
  /** 测试已保存的供应商时传入：Key 前端拿不到（脱敏），由后端自己取 */
  providerId?: number;
  baseUrl?: string;
  apiKey?: string;
  timeoutSeconds?: number;
}

/** 从上游供应商拉取模型列表的结果 */
export interface LlmFetchModelsResult {
  ok: boolean;
  models: string[];
  message: string;
}

/**
 * 从上游供应商拉取模型列表（OpenAI 兼容的 GET /models）。
 * 后端按 timeoutSeconds 等待返回，前端必须比它更晚超时。
 */
export function fetchProviderModels(
  payload: LlmFetchModelsRequest,
): Promise<LlmFetchModelsResult> {
  const waitMs = ((payload.timeoutSeconds ?? 15) + 5) * 1000;
  return request.post<unknown, LlmFetchModelsResult>(
    "/api/settings/llm/providers/models",
    payload,
    { timeout: waitMs },
  );
}

/** 读取某条已保存供应商缓存的完整模型列表（列表接口只回数量） */
export function fetchLlmProviderModels(id: number): Promise<string[]> {
  return request
    .get<unknown, { models: string[] }>(`/api/settings/llm/providers/${id}/models`)
    .then((res) => res.models || []);
}
