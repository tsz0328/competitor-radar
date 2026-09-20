import request from "@/api/request";
import type { NotificationRecord } from "@/types/event";

/** 通知中心列表：高优事件 + 服务端已读态 + 全局未读数 */
export interface NotificationListResult {
  records: NotificationRecord[];
  total: number;
  unread: number;
}

/** 标记已读后的轻量回执：未读数 + 被标记事件 id */
export interface ReadAck {
  unread: number;
  readId?: number | null;
}

/** 通知中心列表（高优事件 + 服务端已读态） */
export function fetchNotifications(params?: {
  limit?: number;
  offset?: number;
}): Promise<NotificationListResult> {
  return request.get<unknown, NotificationListResult>("/api/notifications", { params });
}

/** 标记单条已读，返回未读数 + 事件 id */
export function markNotificationRead(eventId: number): Promise<ReadAck> {
  return request.post<unknown, ReadAck>(`/api/notifications/${eventId}/read`, null);
}

/** 全部已读，返回未读数 */
export function markAllNotificationsRead(): Promise<ReadAck> {
  return request.post<unknown, ReadAck>("/api/notifications/read-all", null);
}

/** 轮询未读数（轻量，不拉列表） */
export function fetchUnreadCount(): Promise<{ unread: number }> {
  return request.get<unknown, { unread: number }>(
    "/api/notifications/unread-count",
  );
}
