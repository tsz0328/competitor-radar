import type { EventDetail, EventRecord } from "@/types/event";

/** 单个 CSV 单元格转义：含逗号/引号/换行的加双引号并转义内部引号 */
function csvCell(v: unknown): string {
  const s = v == null ? "" : String(v);
  if (/[",\n\r]/.test(s)) {
    return `"${s.replace(/"/g, '""')}"`;
  }
  return s;
}

function download(filename: string, content: string, mime: string) {
  const blob = new Blob([content], { type: `${mime};charset=utf-8` });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

/** 列表导出的三种格式（顺序即下拉菜单顺序） */
export type EventExportFormat = "csv" | "markdown" | "json";

/**
 * 导出格式清单：label 给按钮，hint 说明"什么场景选它"，
 * 免得用户只看到 CSV/JSON 这种名词还得猜。
 *
 * 没有做 .xlsx：真·Excel 需要引入写 xlsx 的库（有体积成本），
 * 而带 BOM 的 CSV 双击就能被 Excel 正确打开，对这份数据够用。
 */
export const EVENT_EXPORT_FORMATS: {
  value: EventExportFormat;
  label: string;
  hint: string;
}[] = [
  { value: "csv", label: "CSV", hint: "Excel / 表格软件可直接打开" },
  { value: "markdown", label: "Markdown 表格", hint: "贴进周报、文档或 PR 里" },
  { value: "json", label: "JSON", hint: "原始字段，便于脚本二次处理" },
];

/** 列头（CSV 与 JSON 的字段口径保持一致） */
const LIST_COLUMNS = [
  "ID",
  "检测日期",
  "检测时间",
  "竞品",
  "类型",
  "标题",
  "优先级",
  "AI置信度",
  "关键词",
  "摘要",
] as const;

/** 一条记录 → 与列头一一对应的值 */
function rowValues(r: EventRecord): (string | number)[] {
  return [
    r.id,
    r.date,
    r.time,
    r.brand,
    r.tag,
    r.title,
    r.priority,
    r.aiConfidence,
    r.keywords?.join(" / ") ?? "",
    r.desc ?? r.summary ?? "",
  ];
}

/** 导出情报事件列表为 CSV（带 BOM，Excel 可直接打开中文不乱码） */
export function exportEventsCsv(
  records: EventRecord[],
  filename = "情报事件.csv",
) {
  const rows = records.map((r) => rowValues(r).map(csvCell).join(","));
  const content =
    "\ufeff" + [LIST_COLUMNS.map(csvCell).join(","), ...rows].join("\r\n");
  download(filename, content, "text/csv");
}

/** Markdown 单元格：竖线与换行会破坏表格结构，转义掉 */
function mdCell(v: unknown): string {
  return String(v ?? "")
    .replace(/\|/g, "\\|")
    .replace(/\r?\n/g, " ");
}

/** 导出情报事件列表为 Markdown 表格 */
export function exportEventsMarkdown(
  records: EventRecord[],
  filename = "情报事件.md",
) {
  const head = `| ${LIST_COLUMNS.join(" | ")} |`;
  const sep = `| ${LIST_COLUMNS.map(() => "---").join(" | ")} |`;
  const rows = records.map(
    (r) => `| ${rowValues(r).map(mdCell).join(" | ")} |`,
  );
  const content = [`# 情报事件（共 ${records.length} 条）`, "", head, sep, ...rows, ""];
  download(filename, content.join("\n"), "text/markdown");
}

/** 导出情报事件列表为 JSON（字段用英文键，便于脚本消费） */
export function exportEventsJson(
  records: EventRecord[],
  filename = "情报事件.json",
) {
  const data = records.map((r) => ({
    id: r.id,
    date: r.date,
    time: r.time,
    competitor: r.brand,
    competitorId: r.competitorId ?? null,
    type: r.tag,
    category: r.category,
    title: r.title,
    priority: r.priority,
    aiConfidence: r.aiConfidence,
    keywords: r.keywords ?? [],
    summary: r.desc ?? r.summary ?? "",
  }));
  download(filename, JSON.stringify(data, null, 2), "application/json");
}

/** 按所选格式导出列表（事件流页「导出表格」菜单的统一入口） */
export function exportEvents(
  records: EventRecord[],
  format: EventExportFormat = "csv",
) {
  if (format === "markdown") return exportEventsMarkdown(records);
  if (format === "json") return exportEventsJson(records);
  return exportEventsCsv(records);
}

/** 导出单条情报事件详情为 Markdown 文件 */
export function exportEventMarkdown(d: EventDetail, filename?: string) {
  const lines: string[] = [];
  lines.push(`# ${d.title}`, "");
  lines.push(
    `- 竞品：${d.brand}${d.brandDesc ? `（${d.brandDesc}）` : ""}`,
  );
  lines.push(`- 类型：${d.tag}`);
  lines.push(`- 优先级：${d.priority}`);
  lines.push(`- 检测时间：${d.date} ${d.time}（${d.ago}）`);
  lines.push(`- AI 置信度：${d.aiConfidence}%`);
  if (d.keywords?.length) lines.push(`- 关键词：${d.keywords.join("、")}`);
  lines.push("", "## AI 摘要", "", d.summary ?? "", "");
  if (d.aiAnalysis) {
    lines.push("## AI 判断（仅供参考）", "", d.aiAnalysis, "");
  }
  if (d.diffDetail) {
    lines.push("## 变化内容", "", "```diff", d.diffDetail, "```", "");
  }
  if (d.url || d.domain) {
    lines.push(`- 竞品官网：${d.url || d.domain}`);
  }
  if (d.sourceUrl) {
    lines.push(`- 监控页面：${d.sourceUrl}`);
  }
  download(filename ?? `情报事件-${d.id}.md`, lines.join("\n"), "text/markdown");
}
