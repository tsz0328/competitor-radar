import request from "@/api/request";

export interface LlmStatus {
  /** real = 走真实模型；mock = 规则兜底 */
  mode: "real" | "mock";
  enabled: boolean;
  hasApiKey: boolean;
  baseUrl: string;
  model: string;
  timeoutSeconds: number;
  minChangeLines: number;
  message: string;
}

/** 查询当前 LLM 是真实模型还是规则 Mock，以及所用端点/模型（无副作用）。 */
export function fetchLlmStatus(): Promise<LlmStatus> {
  return request.get<unknown, LlmStatus>("/api/llm/status");
}
