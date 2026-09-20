import { defineStore } from "pinia";
import { ref } from "vue";
import {
  fetchNotifications,
  fetchUnreadCount,
  markNotificationRead,
  markAllNotificationsRead,
} from "@/api/notification";
import type { NotificationRecord } from "@/types/event";

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

  function isRead(id: number) {
    const item = notifications.value.find((n) => n.id === id);
    return item ? item.isRead : false;
  }

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
    } catch {
      /* 轮询失败静默：网络抖动/令牌过期不应打断界面 */
    }
  }

  /** SSE 实时推送：直接设置未读数（不触发请求） */
  function setUnread(n: number) {
    unreadCount.value = n;
  }

  return {
    notifications,
    loading,
    unreadCount,
    load,
    isRead,
    markRead,
    markAllRead,
    refreshUnread,
    setUnread,
  };
});
