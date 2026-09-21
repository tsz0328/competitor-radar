/**
 * 事件详情抽屉的等待态。
 *
 * 背景：从通知中心（或周报）带 id 跳进情报中心时，抽屉会立刻滑出，而详情还在路上。
 * 这时如果什么都不渲染，用户看到的就是"半屏白板"，所以加载中必须有骨架屏。
 */
import { describe, expect, it, vi, beforeEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import ElementPlus from "element-plus";

const { store } = vi.hoisted(() => ({
  store: {
    detailLoading: true,
    eventDetail: null as unknown,
    relatedLoading: false,
    relatedEvents: [] as unknown[],
    loadEventDetail: vi.fn(),
    loadRelatedEvents: vi.fn(),
  },
}));

vi.mock("@/stores/event", () => ({ useEventStore: () => store }));
vi.mock("@/api/event", () => ({
  fetchEventSnapshots: vi.fn().mockResolvedValue([]),
  fetchSnapshotRaw: vi.fn().mockResolvedValue(""),
}));
vi.mock("@/utils/exportEvents", () => ({ exportEventMarkdown: vi.fn() }));
vi.mock("vue-router", () => ({ useRouter: () => ({ push: vi.fn() }) }));

import EventDetailDrawer from "@/components/EventDetailDrawer.vue";

const DETAIL = {
  id: 1,
  brand: "deepseek",
  tag: "价格变化",
  tagType: "price",
  priority: "高",
  priorityType: "high",
  title: "定价页变化：新增 deepseek-flash",
  summary: "对比上次抓取，定价页新增 5 行、移除 6 行",
  keywords: ["定价"],
  aiAnalysis: "可能影响使用成本",
  aiConfidence: 88,
  iconText: "D",
  iconBg: "#e8f0fe",
  iconColor: "#1a73e8",
  date: "2026-09-19",
  time: "17:29",
  ago: "1 天前",
  source: "定价页",
  sourceUrl: "",
  url: "",
  domain: "deepseek.com",
  diffDetail: "",
};

/** el-drawer 默认 teleport 到 body，stub 掉 teleport 才能用 wrapper 直接断言 */
function mountDrawer() {
  return mount(EventDetailDrawer, {
    props: { modelValue: true, eventId: 1 },
    global: { plugins: [ElementPlus], stubs: { teleport: true } },
  });
}

beforeEach(() => {
  store.detailLoading = true;
  store.eventDetail = null;
  store.loadEventDetail.mockReset().mockResolvedValue(null);
  store.loadRelatedEvents.mockReset().mockResolvedValue(undefined);
});

describe("事件详情抽屉 - 等待态", () => {
  it("加载中渲染骨架屏，而不是空白的抽屉", async () => {
    const wrapper = mountDrawer();
    await flushPromises();

    expect(wrapper.find(".el-skeleton").exists()).toBe(true);
    // 不该误报"加载失败"
    expect(wrapper.text()).not.toContain("没能加载这条情报");
  });

  it("加载完成后渲染真实详情，骨架屏消失", async () => {
    store.detailLoading = false;
    store.eventDetail = DETAIL;

    const wrapper = mountDrawer();
    await flushPromises();

    expect(wrapper.find(".el-skeleton").exists()).toBe(false);
    expect(wrapper.text()).toContain(DETAIL.title);
    expect(wrapper.text()).toContain("价格变化");
  });
});
