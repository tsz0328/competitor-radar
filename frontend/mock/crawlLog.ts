import { authUser, db, err, ok } from "./db";

function requireUser(headers: any) {
  return authUser(headers) || null;
}

export default [
  {
    url: "/api/crawl-logs",
    method: "get",
    timeout: 200,
    response: ({ headers, query }: any) => {
      const u = requireUser(headers);
      if (!u) return err(40100, "未登录或登录已过期");
      const d = db();
      const q = query || {};
      const page = Number(q.page) || 1;
      const pageSize = Number(q.pageSize) || 20;
      const status = q.status || null;
      const trigger = q.trigger || null;
      const competitorId = q.competitorId ? Number(q.competitorId) : null;

      const filtered = d.crawlLogs
        .filter((l: any) => l.userId === u.id)
        .filter((l: any) => !status || l.status === status)
        .filter((l: any) => !trigger || l.trigger === trigger)
        .filter((l: any) => competitorId == null || l.competitorId === competitorId)
        .sort((a: any, b: any) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime());

      const total = filtered.length;
      const items = filtered.slice((page - 1) * pageSize, page * pageSize);
      return ok({ items, total, page, pageSize });
    },
  },
  {
    url: "/api/crawl-logs",
    method: "delete",
    timeout: 200,
    response: ({ headers }: any) => {
      const u = requireUser(headers);
      if (!u) return err(40100, "未登录或登录已过期");
      const d = db();
      d.crawlLogs = d.crawlLogs.filter((l: any) => l.userId !== u.id);
      return ok(null);
    },
  },
];