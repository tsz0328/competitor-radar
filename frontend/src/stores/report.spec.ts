import { describe, it, expect, vi, beforeEach } from "vitest";
import { createPinia, setActivePinia } from "pinia";
import { useReportStore } from "@/stores/report";
import { fetchReportDetail } from "@/api/report";

vi.mock("@/api/report", () => ({
  fetchReportList: vi.fn(),
  fetchReportDetail: vi.fn(),
}));

beforeEach(() => {
  setActivePinia(createPinia());
  vi.clearAllMocks();
});

describe("report store 请求竞态守卫", () => {
  it("详情：旧详情不覆盖新详情", async () => {
    let resolveFirst: (v: unknown) => void = () => {};
    vi.mocked(fetchReportDetail)
      .mockImplementationOnce(() => new Promise((res) => (resolveFirst = res)) as any)
      .mockResolvedValueOnce({ id: 2, favorite: false } as any);

    const store = useReportStore();
    const p1 = store.loadReportDetail(1);
    const p2 = store.loadReportDetail(2);
    await p2;
    resolveFirst({ id: 1, favorite: false });
    await p1;

    expect(store.reportDetail?.id).toBe(2);
  });
});
