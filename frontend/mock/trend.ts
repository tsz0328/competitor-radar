import { authUser, db, err, idFrom, ok, ownedCompetitorIds } from "./db";

function requireUser(headers: any) {
  return authUser(headers) || null;
}

// ---------- 确定性伪随机，保证每次刷新曲线稳定 ----------
function mulberry32(seed: number) {
  let a = seed >>> 0;
  return () => {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function dayIndex(d: Date): number {
  return Math.floor(d.getTime() / 86400000);
}

function parseDays(query: any): number {
  const n = Number(query?.days) || 90;
  return [7, 30, 90].includes(n) ? n : 7;
}

/** 生成一段每日趋势（feature/price/sentiment/content/other） */
function buildPoints(days: number, seed: number) {
  const now = new Date();
  const out: any[] = [];
  let feature = 8 + (seed % 7);
  let sentiment = 4 + (seed % 5);
  for (let i = days - 1; i >= 0; i--) {
    const d = new Date(now.getTime() - i * 86400000);
    const rng = mulberry32(dayIndex(d) * 7 + seed * 131);
    const step = Math.floor(rng() * 5) - 2;
    feature = Math.max(0, feature + step + (seed % 2 === 0 ? 1 : 0));
    sentiment = Math.max(0, sentiment + (Math.floor(rng() * 3) - 1));
    out.push({
      date: `${d.getMonth() + 1}/${d.getDate()}`,
      feature,
      price: Math.max(0, Math.floor(rng() * 8) + (seed % 3)),
      sentiment,
      content: Math.max(0, Math.floor(rng() * 12) + (seed % 4)),
      other: Math.max(0, Math.floor(rng() * 4)),
    });
  }
  return out;
}

function countOf(p: any): number {
  return p.feature + p.price + p.sentiment + p.content + p.other;
}

export default [
  {
    url: "/api/trends/daily",
    method: "get",
    timeout: 200,
    response: ({ headers, query }: any) => {
      if (!requireUser(headers)) return err(40100, "未登录或登录已过期");
      const days = parseDays(query);
      const points = buildPoints(days, 1);
      return ok(
        points.map((p: any, i: number) => {
          const d = new Date(Date.now() - (days - 1 - i) * 86400000);
          const mm = String(d.getMonth() + 1).padStart(2, "0");
          const dd = String(d.getDate()).padStart(2, "0");
          return { date: `${d.getMonth() + 1}/${d.getDate()}`, dateIso: `${d.getFullYear()}-${mm}-${dd}`, count: countOf(p) };
        }),
      );
    },
  },
  {
    url: "/api/trends/overview",
    method: "get",
    timeout: 200,
    response: ({ headers, query }: any) => {
      if (!requireUser(headers)) return err(40100, "未登录或登录已过期");
      return ok(buildPoints(parseDays(query), 1));
    },
  },
  {
    url: "/api/trends/compare",
    method: "get",
    timeout: 200,
    response: ({ headers, query }: any) => {
      const u = requireUser(headers);
      if (!u) return err(40100, "未登录或登录已过期");
      const d = db();
      const days = parseDays(query);
      const comps = d.competitors.filter((c) => c.userId === u.id && !c.deletedAt && c.status === "active").slice(0, 6);
      return ok(
        comps.map((c) => ({
          competitorId: c.id,
          competitorName: c.name,
          points: buildPoints(days, c.id).map((p: any) => ({ date: p.date, count: countOf(p) })),
        })),
      );
    },
  },
  {
    url: "/api/trends/:id/chart",
    method: "get",
    timeout: 200,
    response: ({ headers, url, query }: any) => {
      const u = requireUser(headers);
      if (!u) return err(40100, "未登录或登录已过期");
      const id = idFrom(url);
      if (!ownedCompetitorIds(u.id).has(id)) return err(40401, "竞品不存在");
      return ok(buildPoints(parseDays(query), id));
    },
  },
  {
    url: "/api/trends/:id",
    method: "get",
    timeout: 1500,
    response: ({ headers, url, query }: any) => {
      const u = requireUser(headers);
      if (!u) return err(40100, "未登录或登录已过期");
      const d = db();
      const id = idFrom(url);
      const c = d.competitors.find((x) => x.id === id && x.userId === u.id && !x.deletedAt);
      if (!c) return err(40401, "竞品不存在");
      const periodDays = Number(query?.periodDays) || 30;
      const points = buildPoints(periodDays, id);
      const total = points.reduce((a: number, p: any) => a + countOf(p), 0);
      const high = points.reduce((a: number, p: any) => a + p.feature, 0);
      const direction = total > periodDays * 22 ? "rising" : total > periodDays * 12 ? "stable" : "declining";
      const label = direction === "rising" ? "活跃度上升" : direction === "stable" ? "活跃度平稳" : "活跃度下降";
      const related = d.events.filter((e) => e.competitorId === id).slice(0, 3);
      return ok({
        competitorId: id,
        competitorName: c.name,
        periodDays,
        direction,
        directionLabel: label,
        summary: `${c.name} 近 ${periodDays} 天共监测到 ${total} 处变化，整体${label}，主要集中在功能更新与内容迭代。`,
        highlights: related.length
          ? related.map((e) => e.title)
          : [`${c.name} 功能持续迭代`, `定价策略基本稳定`, `舆论整体正面`],
        eventCount: d.events.filter((e) => e.competitorId === id).length,
        highImpactCount: d.events.filter((e) => e.competitorId === id && e.priority === "high").length,
        coverageDays: Math.max(1, Math.min(periodDays, high > 0 ? periodDays : 3)),
        generatedAt: new Date().toISOString(),
      });
    },
  },
];