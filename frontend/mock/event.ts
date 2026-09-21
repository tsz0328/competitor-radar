import {
  EVENT_TYPES,
  authUser,
  cleanHost,
  db,
  err,
  formatDateTime,
  idFrom,
  isoDate,
  isoDateTime,
  ok,
  ownedCompetitorIds,
  serializeEvent,
  serializeEventDetail,
} from "./db";

function requireUser(headers: any) {
  const u = authUser(headers);
  if (!u) return null;
  return u;
}

function competitorOf(d: any, id: number) {
  return d.competitors.find((c) => c.id === id);
}

/** 事件列表：分类总结 + 优先级分面 + 记录（分页），仅限当前用户竞品产生的事件 */
function listEvents(query: any, userId: number) {
  const d = db();
  const compById = Object.fromEntries(d.competitors.map((c) => [c.id, c]));
  const ownIds = ownedCompetitorIds(userId);

  const q = query || {};
  const competitorId = q.competitorId ? Number(q.competitorId) : null;
  const category = q.category || null;
  const priorityList = q.priority
    ? String(q.priority).split(",").filter(Boolean)
    : [];
  const minConf = q.minConfidence != null ? Number(q.minConfidence) : null;
  const maxConf = q.maxConfidence != null ? Number(q.maxConfidence) : null;
  const keyword = (q.keyword || "").trim().toLowerCase();
  const days = q.days != null ? Number(q.days) : null;
  const startDate = q.startDate || null;
  const endDate = q.endDate || null;
  const limit = q.limit != null ? Number(q.limit) : 50;
  const offset = q.offset != null ? Number(q.offset) : 0;

  const base = d.events.filter((e) => {
    if (!ownIds.has(e.competitorId)) return false;
    if (competitorId && e.competitorId !== competitorId) return false;
    if (days) {
      const cutoff = Date.now() - days * 86400000;
      if (new Date(e.createdAt).getTime() < cutoff) return false;
    }
    if (startDate && e.createdAt.slice(0, 10) < startDate) return false;
    if (endDate && e.createdAt.slice(0, 10) > endDate) return false;
    const conf100 = Math.round((e.confidence ?? 0) * 100);
    if (minConf != null && conf100 < minConf) return false;
    if (maxConf != null && conf100 > maxConf) return false;
    if (keyword) {
      const comp = compById[e.competitorId];
      const hay = `${e.title} ${e.summary} ${comp ? comp.name : ""}`.toLowerCase();
      if (!hay.includes(keyword)) return false;
    }
    return true;
  });

  const catOf = (e: any) => EVENT_TYPES[e.eventType]?.category || "other";

  // 分类总结：排除分类自身，但含优先级筛选
  const forCategory = base.filter((e) => !priorityList.length || priorityList.includes(e.priority));
  const summary: any = { total: 0, feature: 0, price: 0, content: 0, negative: 0, other: 0, high: 0, mid: 0, low: 0 };
  for (const e of forCategory) {
    summary.total += 1;
    const cat = catOf(e);
    if (cat in summary) summary[cat] += 1;
  }

  // 优先级分面：排除优先级自身，但含分类筛选
  const forPriority = base.filter((e) => !category || catOf(e) === category);
  for (const e of forPriority) summary[e.priority] += 1;

  // 记录：分类 + 优先级 + 分页
  const filtered = base.filter(
    (e) =>
      (!category || catOf(e) === category) &&
      (!priorityList.length || priorityList.includes(e.priority)),
  );
  const total = filtered.length;
  const records = filtered
    .slice(offset, offset + limit)
    .map((e) => serializeEvent(e, compById[e.competitorId]));

  return { summary, total, records };
}

export default [
  {
    url: "/api/events/daily-insight",
    method: "get",
    timeout: 800,
    response: ({ headers, query }: any) => {
      const u = requireUser(headers);
      if (!u) return err(40100, "未登录或登录已过期");
      const d = db();
      const days = query?.days ? Number(query.days) : 1;
      const cutoff = Date.now() - days * 86400000;
      const compById = Object.fromEntries(d.competitors.map((c) => [c.id, c]));
      const ownIds = ownedCompetitorIds(u.id);
      const recent = d.events.filter((e) => ownIds.has(e.competitorId) && new Date(e.createdAt).getTime() >= cutoff);
      const highCount = recent.filter((e) => e.priority === "high").length;
      const competitorCount = new Set(recent.map((e) => e.competitorId)).size;
      const names = Array.from(new Set(recent.map((e) => compById[e.competitorId]?.name).filter(Boolean)));
      const summaryText =
        recent.length === 0
          ? "暂未发现竞品动态，保持关注。"
          : `近 ${days} 天共监测到 ${recent.length} 条竞品变化，涉及 ${competitorCount} 个竞品，其中高影响 ${highCount} 条。`;
      return ok({
        days,
        periodText: days === 1 ? "过去 24 小时" : `过去 ${days} 天`,
        eventCount: recent.length,
        highCount,
        competitorCount,
        summary: summaryText,
        highlights: names.slice(0, 4).map((n) => `${n} 有新的动态变化`),
        fromLlm: false,
        generatedAt: new Date().toISOString(),
      });
    },
  },
  {
    url: "/api/events/related",
    method: "get",
    timeout: 200,
    response: ({ headers, query }: any) => {
      const u = requireUser(headers);
      if (!u) return err(40100, "未登录或登录已过期");
      const d = db();
      const q = query || {};
      const competitorId = Number(q.competitorId);
      const excludeId = q.excludeId ? Number(q.excludeId) : null;
      const days = q.days ? Number(q.days) : null;
      const category = q.category || null;
      const limit = q.limit ? Number(q.limit) : 8;
      const compById = Object.fromEntries(d.competitors.map((c) => [c.id, c]));
      const ownIds = ownedCompetitorIds(u.id);

      const list = d.events
        .filter((e) => ownIds.has(e.competitorId) && e.competitorId === competitorId)
        .filter((e) => excludeId == null || e.id !== excludeId)
        .filter((e) => !days || new Date(e.createdAt).getTime() >= Date.now() - days * 86400000)
        .filter((e) => !category || (EVENT_TYPES[e.eventType]?.category || "other") === category)
        .slice(0, limit);
      return ok(list.map((e) => serializeEvent(e, compById[e.competitorId])));
    },
  },
  {
    url: "/api/events",
    method: "get",
    timeout: 300,
    response: ({ headers, query }: any) => {
      const u = requireUser(headers);
      if (!u) return err(40100, "未登录或登录已过期");
      return ok(listEvents(query, u.id));
    },
  },
  {
    url: "/api/events/:id/snapshots",
    method: "get",
    timeout: 200,
    response: ({ headers, url, query }: any) => {
      const u = requireUser(headers);
      if (!u) return err(40100, "未登录或登录已过期");
      const d = db();
      const id = idFrom(url);
      const e = d.events.find((x) => x.id === id);
      if (!e || !ownedCompetitorIds(u.id).has(e.competitorId)) return err(40403, "事件不存在");
      const limit = query?.limit ? Number(query.limit) : 10;
      const base = new Date(e.createdAt).getTime();
      const rows = Array.from({ length: Math.min(3, limit) }, (_, i) => {
        const t = new Date(base - i * 6 * 3600000);
        return {
          id: id * 100 + i,
          crawledAt: t.toISOString(),
          crawledAtLabel: formatDateTime(t.toISOString()),
          available: true,
          changeDetected: i === 0,
          isCurrent: i === 0,
        };
      });
      return ok(rows);
    },
  },
  {
    url: "/api/events/:id",
    method: "get",
    timeout: 200,
    response: ({ headers, url }: any) => {
      const u = requireUser(headers);
      if (!u) return err(40100, "未登录或登录已过期");
      const d = db();
      const id = idFrom(url);
      const e = d.events.find((x) => x.id === id);
      if (!e || !ownedCompetitorIds(u.id).has(e.competitorId)) return err(40403, "事件不存在");
      return ok(serializeEventDetail(e, competitorOf(d, e.competitorId)));
    },
  },
  {
    url: "/api/snapshots/:id/raw",
    method: "get",
    rawResponse: async (req: any, res: any) => {
      const snapshotId = idFrom(req.url || "");
      const html = `<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8"><title>快照 #${snapshotId}</title></head><body><h1>页面原始快照</h1><p>抓取时间：${isoDateTime(new Date())}</p><pre>--- 变更差异 ---
+ 新增了定价说明段落
- 旧的价格方案已下线
（此处为 Mock 原始 HTML 内容，仅用于展示快照查看器）</pre></body></html>`;
      res.statusCode = 200;
      res.setHeader("Content-Type", "text/html; charset=utf-8");
      res.end(html);
    },
  },
];