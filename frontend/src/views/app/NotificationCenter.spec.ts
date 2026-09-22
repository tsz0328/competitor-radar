import { describe, it, expect, vi, beforeEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import { createPinia } from "pinia";
import { defineComponent, nextTick } from "vue";
import ElementPlus from "element-plus";
import type { NotificationRecord } from "@/types/event";

// 用 vi.hoisted 共享 mock，避免 vi.mock 提升后引用未初始化的外层变量
const mocks = vi.hoisted(() => ({
  push: vi.fn(),
  fetchNotifications: vi.fn(),
  markNotificationRead: vi.fn(),
  markAllNotificationsRead: vi.fn(),
}));

vi.mock("vue-router", () => ({ useRouter: () => ({ push: mocks.push }) }));
vi.mock("@/api/notification", () => ({
  fetchNotifications: mocks.fetchNotifications,
  markNotificationRead: mocks.markNotificationRead,
  markAllNotificationsRead: mocks.markAllNotificationsRead,
}));

import NotificationCenter from "./NotificationCenter.vue";

/** EventDetailDrawer 桩：只保留 props/事件，方便在测试里手动 emit loaded */
const DrawerStub = defineComponent({
  name: "EventDetailDrawer",
  props: {
    modelValue: { type: Boolean, default: false },
    eventId: { type: Number, default: null },
  },
  emits: ["update:modelValue", "select", "loaded"],
  template: '<div class="drawer-stub" />',
});

function rec(id: number, isRead: boolean): NotificationRecord {
  return {
    id,
    date: "2026-09-22",
    dateLabel: "今天",
    time: "10:00",
    brand: `竞品${id}`,
    brandDesc: "",
    domain: "example.com",
    iconText: "A",
    iconBg: "#eee",
    iconColor: "#333",
    tag: "价格变化",
    tagType: "price",
    title: `事件标题${id}`,
    desc: "描述",
    keywords: [],
    aiConfidence: 90,
    priority: "高",
    priorityType: "high",
    ago: "1 小时前",
    category: "price",
    isRead,
  };
}

function mountPage() {
  return mount(NotificationCenter, {
    global: {
      plugins: [createPinia(), ElementPlus],
      stubs: { EventDetailDrawer: DrawerStub },
    },
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  mocks.fetchNotifications.mockResolvedValue({
    records: [rec(2, false), rec(1, false)],
    total: 2,
    unread: 2,
  });
  mocks.markNotificationRead.mockResolvedValue({ unread: 1, readId: 2 });
  mocks.markAllNotificationsRead.mockResolvedValue({ unread: 0, readId: null });
});

describe("NotificationCenter 通知中心页", () => {
  it("挂载即用 days=0 拉全量归档，并渲染所有通知", async () => {
    const w = mountPage();
    await flushPromises();

    expect(mocks.fetchNotifications).toHaveBeenCalledWith({ days: 0, limit: 200 });
    expect(w.findAll(".nc-item").length).toBe(2);
    expect(w.text()).toContain("共 2 条");
  });

  it("三档筛选：未读 / 已读 只展示对应记录", async () => {
    const w = mountPage();
    await flushPromises();

    (w.vm as unknown as { tab: string }).tab = "read";
    await nextTick();
    expect(w.findAll(".nc-item").length).toBe(0);
    expect(w.text()).toContain("还没有已读通知");

    (w.vm as unknown as { tab: string }).tab = "unread";
    await nextTick();
    expect(w.findAll(".nc-item").length).toBe(2);
  });

  it("点开详情后抽屉主数据加载成功才标已读，该条从未读列表移除", async () => {
    const w = mountPage();
    await flushPromises();

    // 打开第一条（id=2）
    await w.findAll(".nc-item")[0].trigger("click");
    expect((w.vm as unknown as { detailId: number }).detailId).toBe(2);

    // 详情加载失败不会 emit loaded —— 这里先确认未标已读
    expect(mocks.markNotificationRead).not.toHaveBeenCalled();

    // 模拟抽屉主数据加载成功
    w.findComponent(DrawerStub).vm.$emit("loaded", 2);
    await flushPromises();

    expect(mocks.markNotificationRead).toHaveBeenCalledWith(2);
    // 该条翻成已读 → 未读档只剩 1 条
    (w.vm as unknown as { tab: string }).tab = "unread";
    await nextTick();
    expect(w.findAll(".nc-item").length).toBe(1);
  });

  it("全部已读：调用 read-all（days=0）并清空未读", async () => {
    const w = mountPage();
    await flushPromises();

    const btn = w
      .findAll("button")
      .find((b) => b.text().includes("全部已读"));
    expect(btn).toBeTruthy();
    await btn!.trigger("click");
    await flushPromises();

    expect(mocks.markAllNotificationsRead).toHaveBeenCalledWith(0);
    (w.vm as unknown as { tab: string }).tab = "unread";
    await nextTick();
    expect(w.findAll(".nc-item").length).toBe(0);
  });

  it("「情报中心」按钮跳转到事件详情深链（带 notify=1）", async () => {
    const w = mountPage();
    await flushPromises();

    const go = w
      .findAll("button")
      .find((b) => b.text().includes("情报中心"));
    expect(go).toBeTruthy();
    await go!.trigger("click");

    expect(mocks.push).toHaveBeenCalledWith({
      name: "Event",
      query: { id: "2", notify: "1" },
    });
  });
});
