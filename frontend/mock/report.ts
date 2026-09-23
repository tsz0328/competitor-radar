import {
  authUser,
  db,
  err,
  idFrom,
  isoDate,
  ok,
} from "./db";

function requireUser(headers: any) {
  return authUser(headers) || null;
}

/** 当前用户自己的报告（忽略回收站） */
function findOwned(d: any, uid: number, id: number) {
  return d.reports.find((x) => x.id === id && x.userId === uid && !x.deletedAt);
}
/** 当前用户回收站里的报告 */
function findOwnedTrash(d: any, uid: number, id: number) {
  return d.reports.find((x) => x.id === id && x.userId === uid && x.deletedAt);
}

/** ISO 周号（与后端 `date.isocalendar()` 口径一致）：返回 (年份, 第几周)。 */
function isoWeekOf(day: Date): { year: number; week: number } {
  const d = new Date(Date.UTC(day.getFullYear(), day.getMonth(), day.getDate()));
  const dayNum = d.getUTCDay() || 7; // 周日=7
  d.setUTCDate(d.getUTCDate() + 4 - dayNum); // 所在周的周四
  const yearStart = new Date(Date.UTC(d.getUTCFullYear(), 0, 1));
  const week = Math.ceil(((d.getTime() - yearStart.getTime()) / 86400000 + 1) / 7);
  return { year: d.getUTCFullYear(), week };
}

function listItem(r: any) {
  const item: any = {
    id: r.id,
    title: r.title,
    type: r.type,
    typeLabel: r.typeLabel,
    range: r.range,
    competitors: r.competitors,
    generatedAt: r.generatedAt,
    favorite: r.favorite,
    monthGroup: r.monthGroup,
  };
  if (r.deletedAt) item.deletedAt = r.deletedAt;
  return item;
}

function detailOf(r: any) {
  return {
    id: r.id,
    type: r.type,
    title: r.title,
    typeLabel: r.typeLabel,
    rangeStart: r.rangeStart,
    rangeEnd: r.rangeEnd,
    competitors: r.competitors,
    favorite: r.favorite,
    summary: r.summary,
    content: r.content,
    stats: r.stats,
    highlights: r.highlights,
    categoryDist: r.categoryDist,
    competitorRank: r.competitorRank,
    impactTrend: r.impactTrend,
    relatedEvents: r.relatedEvents,
    relatedCompetitors: r.relatedCompetitors,
    aiSteps: r.aiSteps,
  };
}

// ---------- Markdown → HTML（供导出 pdf/html 使用） ----------
function escapeHtml(s: string): string {
  return s.replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c] as string));
}
function inline(text: string): string {
  return escapeHtml(text)
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/\*([^*]+)\*/g, "<em>$1</em>")
    .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2">$1</a>');
}
function markdownToHtml(md: string): string {
  const lines = (md || "").split(/\r?\n/);
  const out: string[] = [];
  const listStack: string[] = [];
  const closeLists = () => { while (listStack.length) out.push(`</${listStack.pop()}>`); };
  for (const raw of lines) {
    const line = raw.trimEnd();
    const h = line.match(/^(#{1,6})\s+(.*)$/);
    if (h) {
      closeLists();
      out.push(`<h${h[1].length}>${inline(h[2])}</h${h[1].length}>`);
      continue;
    }
    if (/^\s*[-*]\s+/.test(line)) {
      if (listStack[listStack.length - 1] !== "ul") out.push("<ul>"), listStack.push("ul");
      out.push(`<li>${inline(line.replace(/^\s*[-*]\s+/, ""))}</li>`);
      continue;
    }
    if (/^\s*\d+\.\s+/.test(line)) {
      if (listStack[listStack.length - 1] !== "ol") out.push("<ol>"), listStack.push("ol");
      out.push(`<li>${inline(line.replace(/^\s*\d+\.\s+/, ""))}</li>`);
      continue;
    }
    closeLists();
    if (line.trim() === "") continue;
    out.push(`<p>${inline(line)}</p>`);
  }
  closeLists();
  return out.join("\n");
}

function printHtml(r: any): string {
  return `<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>${escapeHtml(r.title)}</title>
<style>body{font-family:-apple-system,'Segoe UI',sans-serif;max-width:800px;margin:40px auto;padding:0 20px;line-height:1.7;color:#222}h1{font-size:26px}h2{font-size:20px;margin-top:28px}ul,ol{padding-left:24px}a{color:#1b5fd9}</style>
</head><body>
${markdownToHtml(r.content)}
</body></html>`;
}

// ---------- 最小合法 docx（STORED zip + CRC32） ----------
const CRC_TABLE: number[] = [];
function crc32(buf: Uint8Array): number {
  if (!CRC_TABLE.length) {
    for (let n = 0; n < 256; n++) {
      let c = n;
      for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
      CRC_TABLE[n] = c >>> 0;
    }
  }
  let crc = 0xffffffff;
  for (let i = 0; i < buf.length; i++) crc = (crc >>> 8) ^ CRC_TABLE[(crc ^ buf[i]) & 0xff];
  return (crc ^ 0xffffffff) >>> 0;
}

function zipStore(files: { name: string; text: string }[]): Buffer {
  const enc = new TextEncoder();
  const entries = files.map((f) => ({ name: Buffer.from(f.name, "utf8"), data: Buffer.from(enc.encode(f.text)) }));
  const parts: Buffer[] = [];
  const central: Buffer[] = [];
  let offset = 0;
  for (const e of entries) {
    const c = crc32(e.data);
    const lh = Buffer.alloc(30);
    lh.writeUInt32LE(0x04034b50, 0);
    lh.writeUInt16LE(20, 4);
    lh.writeUInt16LE(0, 6);
    lh.writeUInt16LE(0, 8);
    lh.writeUInt16LE(0, 10);
    lh.writeUInt16LE(0x21, 12);
    lh.writeUInt32LE(c, 14);
    lh.writeUInt32LE(e.data.length, 18);
    lh.writeUInt32LE(e.data.length, 22);
    lh.writeUInt16LE(e.name.length, 26);
    lh.writeUInt16LE(0, 28);
    parts.push(lh, e.name, e.data);

    const ch = Buffer.alloc(46);
    ch.writeUInt32LE(0x02014b50, 0);
    ch.writeUInt16LE(20, 4);
    ch.writeUInt16LE(20, 6);
    ch.writeUInt16LE(0, 8);
    ch.writeUInt16LE(0, 10);
    ch.writeUInt16LE(0, 12);
    ch.writeUInt16LE(0x21, 14);
    ch.writeUInt32LE(c, 16);
    ch.writeUInt32LE(e.data.length, 20);
    ch.writeUInt32LE(e.data.length, 24);
    ch.writeUInt16LE(e.name.length, 28);
    ch.writeUInt16LE(0, 30);
    ch.writeUInt16LE(0, 32);
    ch.writeUInt16LE(0, 34);
    ch.writeUInt16LE(0, 36);
    ch.writeUInt32LE(0, 38);
    ch.writeUInt32LE(offset, 42);
    central.push(ch, e.name);
    offset += 30 + e.name.length + e.data.length;
  }
  const centralSize = central.reduce((a, b) => a + b.length, 0);
  const eocd = Buffer.alloc(22);
  eocd.writeUInt32LE(0x06054b50, 0);
  eocd.writeUInt16LE(0, 4);
  eocd.writeUInt16LE(0, 6);
  eocd.writeUInt16LE(entries.length, 8);
  eocd.writeUInt16LE(entries.length, 10);
  eocd.writeUInt32LE(centralSize, 12);
  eocd.writeUInt32LE(offset, 16);
  eocd.writeUInt16LE(0, 20);
  return Buffer.concat([...parts, ...central, eocd]);
}

function xmlEscape(s: string): string {
  return s.replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c] as string));
}

function toDocx(r: any): Buffer {
  const paras = (r.content || "").split(/\r?\n/).filter((l: string) => l.trim() !== "")
    .map((l: string) => {
      const h = l.match(/^(#{1,6})\s+(.*)$/);
      const bold = h ? h[2] : l.replace(/^\s*[-*]\s+/, "");
      return `<w:p><w:r><w:t${h || /^\s*[-*]/.test(l) ? ' xml:space="preserve"' : ""}>${xmlEscape(bold)}</w:t></w:r></w:p>`;
    })
    .join("");
  const documentXml = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>${paras}</w:body></w:document>`;
  const contentTypes = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>`;
  const rels = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>`;
  return zipStore([
    { name: "[Content_Types].xml", text: contentTypes },
    { name: "_rels/.rels", text: rels },
    { name: "word/document.xml", text: documentXml },
  ]);
}

// ---------- 生成新报告（周一到今天 / 本月 1 号到今天） ----------
function newReport(type: string): any {
  const template = db().reports[0] || null;
  const base = template ? JSON.parse(JSON.stringify(template)) : { content: "", summary: "" };
  const now = new Date();
  const today = isoDate(now);
  const y = now.getFullYear();
  const m = now.getMonth() + 1;

  let rangeStart = today;
  let title = "";
  let typeLabel = "";
  if (type === "monthly") {
    rangeStart = `${y}-${String(m).padStart(2, "0")}-01`;
    title = `${y}年${m}月 竞品月报`;
    typeLabel = "月报";
  } else {
    const dow = now.getDay(); // 0 周日
    const diff = dow === 0 ? 6 : dow - 1; // 到周一天数
    const monday = new Date(now.getTime() - diff * 86400000);
    rangeStart = isoDate(monday);
    const { year, week } = isoWeekOf(monday);
    title = `${year}年第${week}周 竞品周报`;
    typeLabel = "周报";
  }
  base.type = type === "monthly" ? "monthly" : "weekly";
  base.typeLabel = typeLabel;
  base.title = title;
  base.rangeStart = rangeStart;
  base.rangeEnd = today;
  base.range = `${rangeStart} - ${today}`;
  base.generatedAt = today;
  base.favorite = false;
  base.deletedAt = null;
  base.shareToken = null;
  base.shareExpiresAt = null;
  base.content = `# ${title}\n\n## 核心摘要\n\n本期共监控 ${base.competitors} 个竞品，持续关注 AI 能力迭代与定价策略变化。\n\n## 重点变化\n\n- 竞品持续迭代 AI 功能。\n- 部分产品调整定价策略。\n`;
  return base;
}

export default [
  {
    url: "/api/reports/generate",
    method: "post",
    timeout: 1200,
    response: ({ headers, query }: any) => {
      const u = requireUser(headers);
      if (!u) return err(40100, "未登录或登录已过期");
      const d = db();
      const reportType = query?.reportType === "monthly" ? "monthly" : "weekly";
      const row = newReport(reportType);
      row.id = d.seq.report++;
      row.userId = u.id;
      d.reports.unshift(row);
      return ok({ status: "created", report: detailOf(row) });
    },
  },
  {
    url: "/api/reports/generate-status",
    method: "get",
    timeout: 100,
    response: ({ headers }: any) => {
      // mock 生成为同步完成，不存在「进行中」的报告生成，故始终返回 null
      if (!requireUser(headers)) return err(40100, "未登录或登录已过期");
      return ok({ generating: null });
    },
  },
  {
    url: "/api/reports/trash",
    method: "get",
    timeout: 200,
    response: ({ headers }: any) => {
      const u = requireUser(headers);
      if (!u) return err(40100, "未登录或登录已过期");
      const d = db();
      return ok(d.reports.filter((r) => r.userId === u.id && r.deletedAt).map(listItem));
    },
  },
  {
    url: "/api/reports/trash/:id",
    method: "post",
    timeout: 200,
    response: ({ headers, url }: any) => {
      const u = requireUser(headers);
      if (!u) return err(40100, "未登录或登录已过期");
      const d = db();
      const id = idFrom(url);
      const r = findOwnedTrash(d, u.id, id);
      if (!r) return err(40404, "该报告不在回收站中");
      r.deletedAt = null;
      return ok(listItem(r));
    },
  },
  {
    url: "/api/reports/trash/:id",
    method: "delete",
    timeout: 200,
    response: ({ headers, url }: any) => {
      const u = requireUser(headers);
      if (!u) return err(40100, "未登录或登录已过期");
      const d = db();
      const id = idFrom(url);
      const idx = d.reports.findIndex((x) => x.id === id && x.userId === u.id && x.deletedAt);
      if (idx < 0) return err(40404, "该报告不在回收站中");
      d.reports.splice(idx, 1);
      return ok(null);
    },
  },
  {
    url: "/api/reports/:id/favorite",
    method: "patch",
    timeout: 200,
    response: ({ headers, url, body }: any) => {
      const u = requireUser(headers);
      if (!u) return err(40100, "未登录或登录已过期");
      const d = db();
      const id = idFrom(url);
      const r = findOwned(d, u.id, id);
      if (!r) return err(40404, "报告不存在");
      r.favorite = !!body?.favorite;
      return ok(detailOf(r));
    },
  },
  {
    url: "/api/reports/:id/share",
    method: "post",
    timeout: 200,
    response: ({ headers, url, body }: any) => {
      const u = requireUser(headers);
      if (!u) return err(40100, "未登录或登录已过期");
      const d = db();
      const id = idFrom(url);
      const r = findOwned(d, u.id, id);
      if (!r) return err(40404, "报告不存在");
      r.shareToken = Array(43).fill(0).map(() => "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"[Math.floor(Math.random() * 64)]).join("");
      const days = body?.expiresDays;
      r.shareExpiresAt = days ? new Date(Date.now() + days * 86400000).toISOString() : "";
      return ok({ token: r.shareToken, expiresAt: r.shareExpiresAt });
    },
  },
  {
    url: "/api/reports/:id/share",
    method: "get",
    timeout: 200,
    response: ({ headers, url }: any) => {
      const u = requireUser(headers);
      if (!u) return err(40100, "未登录或登录已过期");
      const d = db();
      const id = idFrom(url);
      const r = findOwned(d, u.id, id);
      if (!r) return err(40404, "报告不存在");
      if (!r.shareToken) return ok(null);
      if (r.shareExpiresAt && new Date(r.shareExpiresAt).getTime() < Date.now()) return ok(null);
      return ok({ token: r.shareToken, expiresAt: r.shareExpiresAt });
    },
  },
  {
    url: "/api/reports/:id/share",
    method: "delete",
    timeout: 200,
    response: ({ headers, url }: any) => {
      const u = requireUser(headers);
      if (!u) return err(40100, "未登录或登录已过期");
      const d = db();
      const id = idFrom(url);
      const r = findOwned(d, u.id, id);
      if (!r) return err(40404, "报告不存在");
      r.shareToken = null;
      r.shareExpiresAt = null;
      return ok({ ok: true });
    },
  },
  {
    url: "/api/reports/:id/export",
    method: "get",
    rawResponse: async (req: any, res: any) => {
      const u = authUser(req.headers);
      if (!u) {
        res.statusCode = 401;
        res.setHeader("Content-Type", "application/json; charset=utf-8");
        return res.end(JSON.stringify({ code: 40100, message: "未登录或登录已过期", data: null }));
      }
      const d = db();
      const id = idFrom(req.url || "");
      const r = d.reports.find((x) => x.id === id && x.userId === u.id && !x.deletedAt);
      const format = new URL(req.url || "", "http://localhost").searchParams.get("format") || "pdf";
      if (!r) {
        res.statusCode = 404;
        res.setHeader("Content-Type", "application/json; charset=utf-8");
        return res.end(JSON.stringify({ code: 40404, message: "报告不存在", data: null }));
      }
      if (format === "docx") {
        res.statusCode = 200;
        res.setHeader("Content-Type", "application/vnd.openxmlformats-officedocument.wordprocessingml.document");
        res.setHeader("Content-Disposition", `attachment; filename="weekly-report-${r.id}.docx"`);
        return res.end(toDocx(r));
      }
      if (format === "md") {
        res.statusCode = 200;
        res.setHeader("Content-Type", "text/markdown; charset=utf-8");
        res.setHeader("Content-Disposition", `attachment; filename="weekly-report-${r.id}.md"`);
        return res.end(r.content);
      }
      // pdf / html：返回打印页 HTML
      res.statusCode = 200;
      res.setHeader("Content-Type", "text/html; charset=utf-8");
      return res.end(printHtml(r));
    },
  },
  {
    url: "/api/reports/:id",
    method: "delete",
    timeout: 200,
    response: ({ headers, url }: any) => {
      const u = requireUser(headers);
      if (!u) return err(40100, "未登录或登录已过期");
      const d = db();
      const id = idFrom(url);
      const r = findOwned(d, u.id, id);
      if (!r) return err(40404, "报告不存在");
      r.deletedAt = new Date().toISOString();
      return ok({ ok: true });
    },
  },
  {
    url: "/api/reports/:id",
    method: "get",
    timeout: 200,
    response: ({ headers, url }: any) => {
      const u = requireUser(headers);
      if (!u) return err(40100, "未登录或登录已过期");
      const d = db();
      const id = idFrom(url);
      const r = findOwned(d, u.id, id);
      if (!r) return err(40404, "报告不存在");
      return ok(detailOf(r));
    },
  },
  {
    url: "/api/reports",
    method: "get",
    timeout: 200,
    response: ({ headers }: any) => {
      const u = requireUser(headers);
      if (!u) return err(40100, "未登录或登录已过期");
      const d = db();
      const reports = d.reports.filter((r) => r.userId === u.id && !r.deletedAt).map(listItem);
      return ok({ total: reports.length, reports });
    },
  },
];