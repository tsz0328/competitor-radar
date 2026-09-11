import { ref } from "vue";
import { defineStore } from "pinia";
import type { EventDetail, EventItem, EventListResult } from "@/types/event";
import { fetchEventDetail, fetchEventList, fetchEvents } from "@/api/event";

export const useEventStore = defineStore("event", () => {
  const loading = ref(false);
  const events = ref<EventItem[]>([]);
  async function loadEvents() {
    loading.value = true;
    try {
      events.value = await fetchEvents();
    } finally {
      loading.value = false;
    }
  }

  // 事件流页面：统计 + 事件记录
  const listLoading = ref(false);
  const eventList = ref<EventListResult | null>(null);
  async function loadEventList() {
    listLoading.value = true;
    try {
      eventList.value = await fetchEventList();
    } finally {
      listLoading.value = false;
    }
  }

  // 事件详情（抽屉用）
  const detailLoading = ref(false);
  const eventDetail = ref<EventDetail | null>(null);
  async function loadEventDetail(id: number) {
    detailLoading.value = true;
    eventDetail.value = null; // 先清空，避免切换事件时闪现上一条内容
    try {
      eventDetail.value = await fetchEventDetail(id);
      return eventDetail.value;
    } finally {
      detailLoading.value = false;
    }
  }

  return {
    loading,
    events,
    loadEvents,
    listLoading,
    eventList,
    loadEventList,
    detailLoading,
    eventDetail,
    loadEventDetail,
  };
});
