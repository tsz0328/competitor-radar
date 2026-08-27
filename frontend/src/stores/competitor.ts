import { ref } from "vue";
import { defineStore } from "pinia";
import type { CompetitorItem } from "@/types/competitor";
import { fetchCompetitors } from "@/api/competitor";

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

  // 开关变更后同步状态列展示（enabled 已由 v-model 翻转，这里只同步展示字段）
  function toggleMonitor(id: number) {
    const item = competitors.value.find((c) => c.id === id);
    if (!item) return;
    item.status = item.enabled ? "监控中" : "已暂停";
    item.statusType = item.enabled ? "success" : "info";
    item.statusDesc = item.enabled ? "正常" : "手动暂停";
  }

  return { loading, competitors, loadCompetitors, toggleMonitor };
});
