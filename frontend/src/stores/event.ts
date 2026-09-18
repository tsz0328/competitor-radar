import { ref } from "vue";
import { defineStore } from "pinia";
import type { DailyInsight, EventDetail, EventListResult, EventRecord } from "@/types/event";
import { fetchDailyInsight, fetchEventDetail, fetchEventList, fetchRelatedEvents } from "@/api/event";

export const useEventStore = defineStore("event", () => {
  // 事件流页 / Dashboard：顶部统计 + 事件记录
  const listLoading = ref(false);
  const eventList = ref<EventListResult | null>(null);
  // 请求序号：快速切换筛选/分页时，丢弃较早的响应，避免"旧结果覆盖新结果"
  let listSeq = 0;
  async function loadEventList(params?: Record<string, unknown>) {
    const seq = ++listSeq;
    listLoading.value = true;
    try {
      const data = await fetchEventList(params);
      if (seq === listSeq) eventList.value = data;
    } finally {
      if (seq === listSeq) listLoading.value = false;
    }
  }

  // 工作台「AI 今日洞察」
  const dailyInsightLoading = ref(false);
  const dailyInsight = ref<DailyInsight | null>(null);
  async function loadDailyInsight(days = 1) {
    dailyInsightLoading.value = true;
    try {
      dailyInsight.value = await fetchDailyInsight(days);
    } finally {
      dailyInsightLoading.value = false;
    }
  }

  // 事件详情（公共抽屉组件用）
  const detailLoading = ref(false);
  const eventDetail = ref<EventDetail | null>(null);
  let detailSeq = 0;
  async function loadEventDetail(id: number) {
    const seq = ++detailSeq;
    detailLoading.value = true;
    eventDetail.value = null; // 先清空，避免切换事件时闪现上一条内容
    try {
      const data = await fetchEventDetail(id);
      if (seq !== detailSeq) return undefined; // 已被更新的请求取代
      eventDetail.value = data;
      return data;
    } finally {
      if (seq === detailSeq) detailLoading.value = false;
    }
  }

  // 相关事件（详情抽屉内"相关事件"列表用）
  const relatedLoading = ref(false);
  const relatedEvents = ref<EventRecord[]>([]);
  let relatedSeq = 0;
  async function loadRelatedEvents(
    competitorId: number,
    excludeId: number,
    options?: { days?: number; category?: string; limit?: number },
  ) {
    const seq = ++relatedSeq;
    relatedEvents.value = []; // 先清空，避免切换事件时闪现上一条的关联
    relatedLoading.value = true;
    try {
      const data = await fetchRelatedEvents({
        competitorId,
        excludeId,
        limit: options?.limit ?? 8,
        days: options?.days,
        category: options?.category,
      });
      if (seq === relatedSeq) relatedEvents.value = data;
    } finally {
      if (seq === relatedSeq) relatedLoading.value = false;
    }
  }

  return {
    listLoading,
    eventList,
    loadEventList,
    dailyInsightLoading,
    dailyInsight,
    loadDailyInsight,
    detailLoading,
    eventDetail,
    loadEventDetail,
    relatedLoading,
    relatedEvents,
    loadRelatedEvents,
  };
});
