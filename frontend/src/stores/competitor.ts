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

/**
 * 竞品新增/编辑弹窗会话：每个会话=一个弹窗实例（可见 或 后台运行中）。
 * 会话放在 store 并挂载在 AppLayout 全局层，「后台进行」隐藏弹窗后任务不中断，
 * 切换页面后右下角悬浮窗仍可点开恢复；支持多个会话同时后台运行。
 */
export interface CompetitorFormSession {
  id: number;
  visible: boolean;
  /** 非空=编辑模式（传入竞品），空=新增 */
  competitor: CompetitorItem | null;
  /** true=弹窗已隐藏、任务仍在后台运行（会话保留）；false=普通开关状态 */
  background: boolean;
}

export const useCompetitorStore = defineStore("competitor", () => {
  const loading = ref(false);
  const competitors = ref<CompetitorItem[]>([]);
  /** 正在抓取中的竞品 id：放 store 而非组件，切换页面后状态不丢，按钮仍显示「抓取中」 */
  const crawlingId = ref<number | null>(null);

  let formSessionSeq = 0;
  const formSessions = ref<CompetitorFormSession[]>([]);

  /** 打开一个新的新增/编辑弹窗会话，返回会话 id */
  function openForm(competitor: CompetitorItem | null): number {
    const id = ++formSessionSeq;
    formSessions.value.push({ id, visible: true, competitor, background: false });
    return id;
  }

  /** 关闭并销毁一个会话（普通关闭或后台任务结束自动收起） */
  function closeForm(id: number) {
    const idx = formSessions.value.findIndex((s) => s.id === id);
    if (idx >= 0) formSessions.value.splice(idx, 1);
  }

  /** 标记会话是否处于「后台运行」模式（AppLayout 据此决定关闭时是保留还是销毁） */
  function setFormBackground(id: number, bg: boolean) {
    const s = formSessions.value.find((x) => x.id === id);
    if (s) s.background = bg;
  }

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
    crawlingId,
    formSessions,
    openForm,
    closeForm,
    setFormBackground,
    loadCompetitors,
    addCompetitor,
    editCompetitor,
    removeCompetitor,
    runCrawl,
    reviveSources,
    toggleMonitor,
  };
});
