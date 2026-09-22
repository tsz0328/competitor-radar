import { ref } from "vue";
import { defineStore } from "pinia";
import type { ReportDetail, ReportListResult } from "@/types/report";
import {
  fetchReportDetail,
  fetchReportList,
  setReportFavorite,
} from "@/api/report";

export const useReportStore = defineStore("report", () => {
  /** 正在生成中的报告类型（weekly/monthly）：放 store 而非组件，切换页面后按钮状态不丢 */
  const generating = ref<"" | "weekly" | "monthly">("");

  // 报告列表
  const listLoading = ref(false);
  const reportList = ref<ReportListResult | null>(null);
  let listSeq = 0;
  async function loadReportList() {
    const seq = ++listSeq;
    listLoading.value = true;
    try {
      const list = await fetchReportList();
      if (seq !== listSeq) return; // 已有更新的请求，丢弃本次
      reportList.value = list;
    } finally {
      if (seq === listSeq) listLoading.value = false;
    }
  }

  // 报告详情
  const detailLoading = ref(false);
  const reportDetail = ref<ReportDetail | null>(null);
  let detailSeq = 0;
  async function loadReportDetail(id: number) {
    const seq = ++detailSeq;
    detailLoading.value = true;
    try {
      const detail = await fetchReportDetail(id);
      if (seq !== detailSeq) return; // 快速切换报告时，避免旧详情覆盖新详情
      reportDetail.value = detail;
    } finally {
      if (seq === detailSeq) detailLoading.value = false;
    }
  }

  /**
   * 切换收藏：写服务端（跟着账号走），成功后同步列表项与当前详情。
   * 失败时抛错，由调用方提示；不做乐观更新，避免与服务端状态不一致。
   */
  async function toggleFavorite(id: number): Promise<boolean> {
    const item = reportList.value?.reports.find((r) => r.id === id);
    const current =
      reportDetail.value?.id === id
        ? reportDetail.value.favorite
        : (item?.favorite ?? false);
    const next = !current;

    const detail = await setReportFavorite(id, next);
    if (item) item.favorite = next;
    if (reportDetail.value?.id === id) reportDetail.value.favorite = next;
    return detail.favorite;
  }

  return {
    listLoading,
    reportList,
    generating,
    loadReportList,
    detailLoading,
    reportDetail,
    loadReportDetail,
    toggleFavorite,
  };
});
