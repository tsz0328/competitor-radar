import { ref } from "vue";
import { defineStore } from "pinia";
import { fetchLlmStatus, type LlmStatus } from "@/api/llm";

/**
 * LLM 运行状态：顶栏徽标与设置页共用。
 * - 顶栏挂载时 refresh 一次
 * - 设置页保存成功后 refresh，徽标立即同步（无需刷新页面）
 */
export const useLlmStore = defineStore("llm", () => {
  const status = ref<LlmStatus | null>(null);

  async function refresh() {
    try {
      status.value = await fetchLlmStatus();
    } catch {
      // 接口异常（如未登录）不阻塞界面，徽标不显示即可
    }
  }

  return { status, refresh };
});
