import { ref } from "vue";
import { defineStore } from "pinia";
import type { ReportDetail, ReportListResult } from "@/types/report";
import { fetchReportList, fetchReportDetail } from "@/api/report";

export const useReportStore = defineStore("report", () => {
  // 收藏状态唯一数据源：左侧列表与右侧详情都以此为准，避免两端各自翻转导致不同步
  const favoriteMap = ref<Record<number, boolean>>({});

  // 报告列表
  const listLoading = ref(false);
  const reportList = ref<ReportListResult | null>(null);
  async function loadReportList() {
    listLoading.value = true;
    try {
      const list = await fetchReportList();
      // 首次加载时用接口数据初始化收藏表，本地已有的修改优先保留
      for (const r of list.reports) {
        if (!(r.id in favoriteMap.value)) {
          favoriteMap.value[r.id] = r.favorite;
        }
      }
      reportList.value = list;
    } finally {
      listLoading.value = false;
    }
  }

  // 报告详情
  const detailLoading = ref(false);
  const reportDetail = ref<ReportDetail | null>(null);
  async function loadReportDetail(id: number) {
    detailLoading.value = true;
    try {
      const detail = await fetchReportDetail(id);
      // 详情每次都从接口重新拉取，需要用收藏表校正，否则本地收藏会被接口值覆盖
      if (id in favoriteMap.value) {
        detail.favorite = favoriteMap.value[id];
      } else {
        favoriteMap.value[id] = detail.favorite;
      }
      reportDetail.value = detail;
    } finally {
      detailLoading.value = false;
    }
  }

  // 收藏切换：以收藏表为准，同步更新列表项与当前详情
  function toggleFavorite(id: number): boolean {
    const next = !favoriteMap.value[id];
    favoriteMap.value[id] = next;
    const item = reportList.value?.reports.find((r) => r.id === id);
    if (item) item.favorite = next;
    if (reportDetail.value?.id === id) {
      reportDetail.value.favorite = next;
    }
    return next;
  }

  return {
    favoriteMap,
    listLoading,
    reportList,
    loadReportList,
    detailLoading,
    reportDetail,
    loadReportDetail,
    toggleFavorite,
  };
});
