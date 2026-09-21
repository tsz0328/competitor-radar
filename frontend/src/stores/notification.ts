import { defineStore } from "pinia";
import { computed, ref } from "vue";
import {
  fetchNotifications,
  fetchUnreadCount,
  markNotificationRead,
  markAllNotificationsRead,
} from "@/api/notification";
import type { NotificationRecord } from "@/types/event";
import { useAuthStore } from "@/stores/auth";

/**
 * 通知中心：消费后端"已推送的高优事件"（priority=high）。
 * 已读态由服务端落库（event_reads），多端一致；刷新不再依赖浏览器 localStorage。
 */

export const useNotificationStore = defineStore("notification", () => {
  const notifications = ref<NotificationRecord[]>([]);
  const loading = ref(false);
  const unreadCount = ref(0);
  let seq = 0;

  /** 拉取高优事件（高优即被推送的通知）+ 服务端已读态 */
  async function load() {
    const s = ++seq;
    loading.value = true;
    try {
      const data = await fetchNotifications({ limit: 50 });
      if (s !== seq) return;
      notifications.value = data.records;
      unreadCount.value = data.unread;
    } finally {
      if (s === seq) loading.value = false;
    }
  }

  /**
   * 通知中心只展示未读：列表是"待处理收件箱"，读过的条目就消失，
   * 未读数继续由角标体现。标记已读后该条会自动从列表里移除。
   */
  const unreadList = computed(() =>
    notifications.value.filter((n) => !n.isRead),
  );

  /** 标记单条已读：调用后端，精确翻转该条 isRead，不覆盖整页列表 */
  async function markRead(id: number) {
    const ack = await markNotificationRead(id);
    const item = notifications.value.find((n) => n.id === id);
    if (item) item.isRead = true;
    unreadCount.value = ack.unread;
  }

  /** 全部已读：调用后端，精确翻转所有条 isRead */
  async function markAllRead() {
    const ack = await markAllNotificationsRead();
    notifications.value.forEach((n) => (n.isRead = true));
    unreadCount.value = ack.unread;
  }

  /** 轮询用：只刷新未读数，不覆盖列表（避免打断用户正在看的通知） */
  async function refreshUnread() {
    try {
      const data = await fetchUnreadCount();
      unreadCount.value = data.unread;
    } catch (e) {
      // 令牌过期（401xx）：显式走统一登出——拦截器其实已清 token 并跳登录，
      // 这里不再「静默吞掉」，让轮询通道也主动登出，挂机用户能感知、不依赖拦截器副作用。
      const code = (
        e as { response?: { data?: { code?: number } } }
      )?.response?.data?.code;
      if (typeof code === "number" && Math.floor(code / 100) === 401) {
        useAuthStore().logout();
      }
      // 其余（网络抖动）静默，不打断界面
    }
  }

  /** SSE 实时推送：直接设置未读数（不触发请求） */
  function setUnread(n: number) {
    unreadCount.value = n;
  }

  return {
    notifications,
    unreadList,
    loading,
    unreadCount,
    load,
    markRead,
    markAllRead,
    refreshUnread,
    setUnread,
  };
});
