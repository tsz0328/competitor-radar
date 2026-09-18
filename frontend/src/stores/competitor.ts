import { ref } from "vue";
import { defineStore } from "pinia";
import type {
  CompetitorCreatePayload,
  CompetitorItem,
  CompetitorUpdatePayload,
} from "@/types/competitor";
import {
  crawlCompetitor as crawlCompetitorApi,
  createCompetitor,
  deleteCompetitor,
  fetchCompetitors,
  reviveSources as reviveSourcesApi,
  updateCompetitor,
} from "@/api/competitor";

export const useCompetitorStore = defineStore("competitor", () => {
  const loading = ref(false);
  const competitors = ref<CompetitorItem[]>([]);

  async function loadCompetitors() {
    loading.value = true;
    try {
      competitors.value = await fetchCompetitors();
    } finally {
      loading.value = false;
    }
  }

  /** 新增竞品：创建成功后重新拉取，保证顺序与派生字段和后端完全一致 */
  async function addCompetitor(payload: CompetitorCreatePayload) {
    const created = await createCompetitor(payload);
    await loadCompetitors();
    return created;
  }

  /** 编辑竞品：保存后重新拉取，保证监控页面/频率等派生字段同步更新 */
  async function editCompetitor(id: number, payload: CompetitorUpdatePayload) {
    const updated = await updateCompetitor(id, payload);
    await loadCompetitors();
    return updated;
  }

  /** 删除竞品：成功后重新拉取列表 */
  async function removeCompetitor(id: number) {
    await deleteCompetitor(id);
    await loadCompetitors();
  }

  /** 立即抓取：跑完刷新列表，让「最近抓取 / 状态 / 失败次数」立刻反映结果 */
  async function runCrawl(id: number) {
    const result = await crawlCompetitorApi(id);
    await loadCompetitors();
    return result;
  }

  /** 一键复活被自动停用的监控源：跑完刷新列表，反映复活后的状态 */
  async function reviveSources(id: number) {
    const updated = await reviveSourcesApi(id);
    await loadCompetitors();
    return updated;
  }

  // 开关变更后同步到后端（enabled 已由 v-model 翻转，这里按新值持久化暂停/开启）
  async function toggleMonitor(id: number) {
    const item = competitors.value.find((c) => c.id === id);
    if (!item) return;
    const willEnable = item.enabled; // 已是切换后的目标值
    // 乐观更新展示字段，避免等待接口期间闪烁
    item.statusLabel = willEnable ? "监控中" : "已暂停";
    item.statusType = willEnable ? "success" : "info";
    item.statusDesc = willEnable ? "正常" : "手动暂停";
    try {
      await updateCompetitor(id, { status: willEnable ? "active" : "paused" });
      await loadCompetitors();
    } catch {
      // 失败回滚：恢复开关与展示
      item.enabled = !willEnable;
      item.statusLabel = !willEnable ? "监控中" : "已暂停";
      item.statusType = !willEnable ? "success" : "info";
      item.statusDesc = !willEnable ? "正常" : "手动暂停";
    }
  }

  return {
    loading,
    competitors,
    loadCompetitors,
    addCompetitor,
    editCompetitor,
    removeCompetitor,
    runCrawl,
    reviveSources,
    toggleMonitor,
  };
});
