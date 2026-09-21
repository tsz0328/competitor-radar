import { authUser, db, err, idFrom, ok, ownedCompetitorIds, serializeEvent } from "./db";

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