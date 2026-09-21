/**
 * 通知中心：顶栏铃铛只列未读。
 *
 * 列表是"待处理收件箱"——读过的条目不再出现，未读数继续由角标体现。
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";
import {
  fetchNotifications,
  markAllNotificationsRead,
  markNotificationRead,
} from "@/api/notification";
import { useNotificationStore } from "@/stores/notification";
import type { NotificationRecord } from "@/types/event";

vi.mock("@/api/notification", () => ({
  fetchNotifications: vi.fn(),
  fetchUnreadCount: vi.fn(),
  markNotificationRead: vi.fn(),
  markAllNotificationsRead: vi.fn(),
}));

/** 测试只关心 id / isRead，其余字段用最小占位（断言不依赖它们） */
function record(id: number, isRead: boolean): NotificationRecord {
  return {
    id,
    brand: "deepseek",
    title: `事件 ${id}`,
    tag: "价格变化",
    tagType: "price",
    priority: "高",
    priorityType: "high",
    ago: "1 天前",
    isRead,
  } as NotificationRecord;
}

beforeEach(() => {
  setActivePinia(createPinia());
  vi.clearAllMocks();
  vi.mocked(fetchNotifications).mockResolvedValue({
    records: [record(1, false), record(2, true), record(3, false)],
    total: 3,
    unread: 2,
  });
  vi.mocked(markNotificationRead).mockResolvedValue({ unread: 1 });
  vi.mocked(markAllNotificationsRead).mockResolvedValue({ unread: 0 });
});

describe("通知中心 - 只显示未读", () => {
  it("拉取后 unreadList 只含未读，已读的仍在 store 但不出现", async () => {
    const store = useNotificationStore();
    await store.load();

    expect(store.notifications).toHaveLength(3);
    expect(store.unreadList.map((n) => n.id)).toEqual([1, 3]);
    expect(store.unreadCount).toBe(2);
  });

  it("标记单条已读 → 该条从列表消失，未读数减少", async () => {
    const store = useNotificationStore();
    await store.load();

    await store.markRead(1);

    expect(store.unreadList.map((n) => n.id)).toEqual([3]);
    expect(store.unreadCount).toBe(1);
  });

  it("全部已读 → 列表清空、角标归零", async () => {
    const store = useNotificationStore();
    await store.load();

    await store.markAllRead();

    expect(store.unreadList).toEqual([]);
    expect(store.unreadCount).toBe(0);
  });
});
