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

/** 导出情报事件列表为 CSV（带 BOM，Excel 可直接打开中文不乱码） */
export function exportEventsCsv(
  records: EventRecord[],
  filename = "情报事件.csv",
) {
  const header = [
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
  ];
  const rows = records.map((r) =>
    [
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
    ]
      .map(csvCell)
      .join(","),
  );
  const content = "﻿" + [header.map(csvCell).join(","), ...rows].join("\r\n");
  download(filename, content, "text/csv");
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
