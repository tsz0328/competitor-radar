/**
 * 情报中心的「快捷时间预设」算法。
 *
 * 口径统一是「含今天」：today 就是今天当天，7d 是从今天往前数 7 个自然日
 *（也就是减 6 天），30d / 90d 同理。90d 与后端 NOTIFICATION_WINDOW_DAYS 的
 * 算法（today - (days - 1)）严格一致，所以「近 90 天」正好覆盖顶栏铃铛的可见范围。
 *
 * 单独抽成纯函数放在这里，是为了能直接单测 —— 之前这段逻辑写在组件里，
 * 「今天」少了一支分支导致按钮点了没反应，还没人发现。
 */
const RANGE_START_OFFSET: Record<string, number> = {
  today: 0,
  "7d": 6,
  "30d": 29,
  "90d": 89,
};

/** 日期格式化成 YYYY-MM-DD（接口与 URL 都用这个格式） */
export function formatDate(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

/**
 * 预设 key → [开始日期, 结束日期]。
 * 未知 key（页面里 `''` 表示"自定义区间"）返回 null，交给日期选择器处理。
 */
export function quickRangeDates(
  key: string,
  base: Date = new Date(),
): [string, string] | null {
  const offset = RANGE_START_OFFSET[key];
  if (offset === undefined) return null;
  const end = new Date(base);
  const start = new Date(base);
  start.setDate(end.getDate() - offset);
  return [formatDate(start), formatDate(end)];
}
