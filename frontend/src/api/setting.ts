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
