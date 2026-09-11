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

  // 开关变更后同步状态列展示（enabled 已由 v-model 翻转，这里只同步展示字段）
  function toggleMonitor(id: number) {
    const item = competitors.value.find((c) => c.id === id);
    if (!item) return;
    item.statusLabel = item.enabled ? "监控中" : "已暂停";
    item.statusType = item.enabled ? "success" : "info";
    item.statusDesc = item.enabled ? "正常" : "手动暂停";
  }

  return {
    loading,
    competitors,
    loadCompetitors,
    addCompetitor,
    editCompetitor,
    removeCompetitor,
    runCrawl,
    toggleMonitor,
  };
});
