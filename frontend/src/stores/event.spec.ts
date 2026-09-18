import { describe, it, expect, vi, beforeEach } from "vitest";
import { createPinia, setActivePinia } from "pinia";
import { useEventStore } from "@/stores/event";
import { fetchEventDetail, fetchEventList } from "@/api/event";

vi.mock("@/api/event", () => ({
  fetchEventList: vi.fn(),
  fetchEventDetail: vi.fn(),
  fetchRelatedEvents: vi.fn(),
}));

beforeEach(() => {
  setActivePinia(createPinia());
  vi.clearAllMocks();
});

describe("event store 请求竞态守卫", () => {
  it("列表：慢的旧响应不覆盖新结果", async () => {
    let resolveFirst: (v: unknown) => void = () => {};
    vi.mocked(fetchEventList)
      .mockImplementationOnce(() => new Promise((res) => (resolveFirst = res)) as any)
      .mockResolvedValueOnce({ records: [{ id: 2 }], total: 1, summary: {} } as any);

    const store = useEventStore();
    const p1 = store.loadEventList({ keyword: "a" });
    const p2 = store.loadEventList({ keyword: "b" });
    await p2;
    resolveFirst({ records: [{ id: 1 }], total: 1, summary: {} });
    await p1;

    expect(store.eventList?.records[0].id).toBe(2);
  });

  it("详情：旧详情不覆盖新详情", async () => {
    let resolveFirst: (v: unknown) => void = () => {};
    vi.mocked(fetchEventDetail)
      .mockImplementationOnce(() => new Promise((res) => (resolveFirst = res)) as any)
      .mockResolvedValueOnce({ id: 2 } as any);

    const store = useEventStore();
    const p1 = store.loadEventDetail(1);
    const p2 = store.loadEventDetail(2);
    await p2;
    resolveFirst({ id: 1 });
    await p1;

    expect(store.eventDetail?.id).toBe(2);
  });
});
