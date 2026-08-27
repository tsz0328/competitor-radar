import { ref } from "vue";
import { defineStore } from "pinia";
import type { EventItem, EventListResult } from "@/types/event";
import { fetchEvents, fetchEventList } from "@/api/event";

export const useEventStore = defineStore("event", () => {
  const loading = ref(false);
  const events = ref<EventItem[]>([]);
  // 和你 useTrendStore.loadTrend() 一模一样的写法
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

  return { loading, events, loadEvents, listLoading, eventList, loadEventList };
});
