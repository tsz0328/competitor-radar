/**
 * 快捷时间预设的算法。
 *
 * 回归点：这段逻辑原先写在组件里，「今天」少了一支分支 —— 点按钮会直接 return，
 * 表现是"今天点不动"。抽成纯函数后在这里钉住。
 */
import { describe, expect, it } from "vitest";
import { formatDate, quickRangeDates } from "@/utils/dateRange";

/** 固定「今天」，避免用例随真实日期漂移 */
const TODAY = new Date(2026, 8, 20); // 2026-09-20

/** 预设跨了多少个自然日（含首尾） */
function spanDays(key: string): number {
  const [start, end] = quickRangeDates(key, TODAY)!;
  return (
    Math.round((new Date(end).getTime() - new Date(start).getTime()) / 86400000) +
    1
  );
}

describe("formatDate", () => {
  it("补零成 YYYY-MM-DD", () => {
    expect(formatDate(new Date(2026, 0, 5))).toBe("2026-01-05");
  });
});

describe("quickRangeDates", () => {
  it("「今天」= 当天到当天", () => {
    expect(quickRangeDates("today", TODAY)).toEqual([
      "2026-09-20",
      "2026-09-20",
    ]);
  });

  it("近 7 / 30 / 90 天的起止日期", () => {
    expect(quickRangeDates("7d", TODAY)).toEqual(["2026-09-14", "2026-09-20"]);
    expect(quickRangeDates("30d", TODAY)).toEqual(["2026-08-22", "2026-09-20"]);
    expect(quickRangeDates("90d", TODAY)).toEqual(["2026-06-23", "2026-09-20"]);
  });

  it("跨度天数与预设名字一致（含今天）", () => {
    expect(spanDays("today")).toBe(1);
    expect(spanDays("7d")).toBe(7);
    expect(spanDays("30d")).toBe(30);
    expect(spanDays("90d")).toBe(90);
  });

  it("未知 key（页面里 '' 表示自定义区间）返回 null", () => {
    expect(quickRangeDates("", TODAY)).toBeNull();
    expect(quickRangeDates("365d", TODAY)).toBeNull();
  });
});
