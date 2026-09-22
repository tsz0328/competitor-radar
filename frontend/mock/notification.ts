import { authUser, db, err, idFrom, ok, ownedCompetitorIds, serializeEvent, userFromToken } from "./db";

function requireUser(headers: any) {
  return authUser(headers) || null;
}

/** 通知候选 = 当前用户名下竞品产生的高优事件（排除回收站竞品），与后端口径一致 */
function highEvents(d: any, uid: number) {
  const ownIds = ownedCompetitorIds(uid);
  return d.events
    .filter((e: any) => e.priority === "high" && ownIds.has(e.competitorId))
    .sort((a: any, b: any) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime());
}

function isRead(d: any, uid: number, eventId: number): boolean {
  return d.eventReads.some((r: any) => r.userId === uid && r.eventId === eventId);
}

function unreadCount(d: any, uid: number) {
  return highEvents(d, uid).filter((e: any) => !isRead(d, uid, e.id)).length;
}

export default [
  {
    url: "/api/notifications",
    method: "get",
    timeout: 200,
    response: ({ headers, query }: any) => {
      const u = requireUser(headers);
      if (!u) return err(40100, "未登录或登录已过期");
      const d = db();
      const limit = query?.limit ? Number(query.limit) : 50;
      const offset = query?.offset ? Number(query.offset) : 0;
      const compById = Object.fromEntries(d.competitors.map((c: any) => [c.id, c]));
      const all = highEvents(d, u.id);
      const records = all.slice(offset, offset + limit).map((e: any) => ({
        ...serializeEvent(e, compById[e.competitorId]),
        isRead: isRead(d, u.id, e.id),
      }));
      return ok({ records, total: all.length, unread: unreadCount(d, u.id) });
    },
  },
  {
    url: "/api/notifications/unread-count",
    method: "get",
    timeout: 200,
    response: ({ headers }: any) => {
      const u = requireUser(headers);
      if (!u) return err(40100, "未登录或登录已过期");
      return ok({ unread: unreadCount(db(), u.id) });
    },
  },
  {
    url: "/api/notifications/stream",
    method: "get",
    // SSE：EventSource 不能带自定义头，令牌走 ?token= 查询参数（与后端 get_current_user_sse 一致）
    rawResponse: (req: any, res: any) => {
      const token = new URL(req.url || "", "http://localhost").searchParams.get("token") || "";
      const user = userFromToken(token);
      if (!user) {
        res.statusCode = 401;
        res.setHeader("Content-Type", "application/json; charset=utf-8");
        res.end(JSON.stringify({ code: 40102, message: "令牌无效或已过期", data: null }));
        return;
      }
      const d = db();
      res.statusCode = 200;
      res.setHeader("Content-Type", "text/event-stream; charset=utf-8");
      res.setHeader("Cache-Control", "no-cache");
      res.setHeader("Connection", "keep-alive");
      res.write(`data: ${JSON.stringify({ unread: unreadCount(d, user.id) })}\n\n`);
      const hb = setInterval(() => res.write(": keep-alive\n\n"), 30_000);
      req.on("close", () => clearInterval(hb));
    },
  },
  {
    url: "/api/notifications/read-all",
    method: "post",
    timeout: 200,
    response: ({ headers }: any) => {
      const u = requireUser(headers);
      if (!u) return err(40100, "未登录或登录已过期");
      const d = db();
      for (const e of highEvents(d, u.id)) {
        if (!isRead(d, u.id, e.id)) d.eventReads.push({ userId: u.id, eventId: e.id });
      }
      return ok({ unread: 0 });
    },
  },
  {
    url: "/api/notifications/:eventId/read",
    method: "post",
    timeout: 200,
    response: ({ headers, url }: any) => {
      const u = requireUser(headers);
      if (!u) return err(40100, "未登录或登录已过期");
      const d = db();
      const eventId = idFrom(url);
      const e = d.events.find((x: any) => x.id === eventId);
      if (!e || !ownedCompetitorIds(u.id).has(e.competitorId)) return err(40403, "事件不存在");
      if (!isRead(d, u.id, eventId)) d.eventReads.push({ userId: u.id, eventId });
      return ok({ unread: unreadCount(d, u.id), readId: eventId });
    },
  },
];