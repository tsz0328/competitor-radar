import {
  EVENT_TYPES,
  adminUser,
  authUser,
  cleanHost,
  db,
  err,
  formatDateTime,
  idFrom,
  isoDate,
  ok,
  ownedCompetitorIdsAll,
  serializeCompetitor,
} from "./db";

function requireAdmin(headers: any) {
  const u = authUser(headers);
  if (!u) return null;
  if (!u.isAdmin) return "forbidden";
  return u;
}

function guard(headers: any) {
  const a = requireAdmin(headers);
  if (a === null) return err(40100, "未登录或登录已过期");
  if (a === "forbidden") return err(40300, "无权限，仅管理员可操作");
  return null;
}

/** 需要拿到管理员对象（写操作要记审计日志）时的鉴权包装 */
function requireAdminOrErr(headers: any): { admin: any; err: any } | null {
  const a = requireAdmin(headers);
  if (a === null) return { admin: null, err: err(40100, "未登录或登录已过期") };
  if (a === "forbidden") return { admin: null, err: err(40300, "无权限，仅管理员可操作") };
  return { admin: a, err: null };
}

const USERNAME_RE = /^[A-Za-z0-9_-]{3,30}$/;

/** 通用分页：返回 { items, total } */
function pageSlice(list: any[], page: number, size: number) {
  const p = Math.max(1, Number(page) || 1);
  const s = Math.max(1, Number(size) || 10);
  return { items: list.slice((p - 1) * s, p * s), total: list.length };
}

function ownerName(d: any, uid: number): string {
  const u = d.users.find((x: any) => x.id === uid);
  return u ? u.username || "" : "";
}

/** 近 N 天逐日计数（按 createdAt 的日期分组，缺日补 0） */
function buildDaily(rows: any[], days: number) {
  const counts = new Map<string, number>();
  for (const r of rows) {
    const iso = (r.createdAt || "").slice(0, 10);
    if (iso) counts.set(iso, (counts.get(iso) || 0) + 1);
  }
  const now = new Date();
  const out: any[] = [];
  for (let i = days - 1; i >= 0; i--) {
    const d = new Date(now.getTime() - i * 86400000);
    const iso = isoDate(d);
    out.push({ date: `${d.getMonth() + 1}/${d.getDate()}`, date_iso: iso, count: counts.get(iso) || 0 });
  }
  return out;
}

/** 某用户名下的情报事件（按竞品归属，含已软删竞品，历史留痕） */
function userEvents(d: any, uid: number) {
  const ids = ownedCompetitorIdsAll(uid);
  return d.events.filter((e: any) => ids.has(e.competitorId));
}

function logAudit(d: any, admin: any, action: string, targetType: string, targetId: number | null, detail: string) {
  d.auditLogs.unshift({
    id: d.seq.auditLog++,
    adminUsername: admin.username,
    action,
    targetType,
    targetId,
    detail,
    createdAt: new Date().toISOString(),
  });
}

function auditOut(a: any) {
  return {
    id: a.id,
    admin_username: a.adminUsername,
    action: a.action,
    target_type: a.targetType,
    target_id: a.targetId ?? null,
    detail: a.detail,
    created_at: formatDateTime(a.createdAt),
  };
}

function annOut(a: any) {
  return { id: a.id, content: a.content, is_active: !!a.is_active, created_at: a.createdAt };
}

export default [
  // ---------------- 系统设置 ----------------
  {
    url: "/api/admin/system-settings",
    method: "get",
    timeout: 200,
    response: ({ headers }: any) => {
      const g = guard(headers);
      if (g) return g;
      return ok(db().systemSettings);
    },
  },
  {
    url: "/api/admin/system-settings",
    method: "put",
    timeout: 200,
    response: ({ headers, body }: any) => {
      const a = requireAdminOrErr(headers);
      if (a!.err) return a!.err;
      const s = db().systemSettings;
      const p = body || {};
      if (p.smtp_host !== undefined) s.smtp_host = p.smtp_host || "";
      if (p.smtp_port !== undefined) s.smtp_port = p.smtp_port || 25;
      if (p.smtp_username !== undefined) s.smtp_username = p.smtp_username || "";
      if (p.smtp_sender !== undefined) s.smtp_sender = p.smtp_sender || "";
      // 授权码：空串 = 不改动；非空 = 更新（明文不回传，仅标记 set）
      if (p.smtp_password !== undefined && p.smtp_password !== "") {
        s.smtp_password_set = true;
        s._password = p.smtp_password;
      }
      logAudit(db(), a!.admin, "update_system_settings", "system_settings", null, "更新系统设置");
      return ok(s);
    },
  },
  {
    url: "/api/admin/system-settings/test-email",
    method: "post",
    timeout: 300,
    response: ({ headers, body }: any) => {
      const a = requireAdminOrErr(headers);
      if (a!.err) return a!.err;
      const to = ((body?.to || "") as string).trim();
      if (!to) return err(40006, "收件人邮箱不能为空");
      return ok({ ok: true, message: `测试邮件已发送至 ${to}` });
    },
  },

  // ---------------- 平台总览 ----------------
  {
    url: "/api/admin/overview",
    method: "get",
    timeout: 300,
    response: ({ headers }: any) => {
      const g = guard(headers);
      if (g) return g;
      const d = db();
      const active = d.competitors.filter((c: any) => !c.deletedAt);
      const totals = {
        users: d.users.length,
        active_users: d.users.filter((u: any) => u.active).length,
        admin_users: d.users.filter((u: any) => u.isAdmin).length,
        competitors: active.length,
        sources: active.reduce((n: number, c: any) => n + (c.sources?.length || 0), 0),
        events: d.events.length,
        reports: d.reports.filter((r: any) => !r.deletedAt).length,
        crawl_logs: d.crawlLogs.length,
      };
      return ok({
        totals,
        event_trend: buildDaily(d.events, 30),
        crawl_trend: buildDaily(d.crawlLogs, 30),
      });
    },
  },

  // ---------------- 用户管理 ----------------
  {
    url: "/api/admin/users",
    method: "get",
    timeout: 200,
    response: ({ headers, query }: any) => {
      const g = guard(headers);
      if (g) return g;
      const d = db();
      const keyword = ((query?.keyword || "") as string).trim().toLowerCase();
      const list = d.users
        .filter((u: any) => {
          if (!keyword) return true;
          return (u.username || "").toLowerCase().includes(keyword) || (u.email || "").toLowerCase().includes(keyword);
        })
        .map(adminUser);
      return ok(pageSlice(list, query?.page, query?.page_size));
    },
  },
  {
    url: "/api/admin/users/:id/overview",
    method: "get",
    timeout: 200,
    response: ({ headers, url }: any) => {
      const g = guard(headers);
      if (g) return g;
      const d = db();
      const id = idFrom(url);
      const u = d.users.find((x: any) => x.id === id);
      if (!u) return err(40402, "用户不存在");
      const comps = d.competitors.filter((c: any) => c.userId === id);
      const events = userEvents(d, id);
      const reports = d.reports.filter((r: any) => r.userId === id);
      const logs = d.crawlLogs.filter((l: any) => l.userId === id);
      return ok({
        id: u.id,
        username: u.username,
        email: u.email || "",
        nickname: u.name || "",
        is_admin: u.isAdmin,
        is_active: u.active,
        created_at: u.createdAt ? formatDateTime(u.createdAt) : "",
        last_login_at: u.lastLoginAt ? formatDateTime(u.lastLoginAt) : "",
        competitor_count: comps.filter((c: any) => !c.deletedAt).length,
        event_count: events.length,
        report_count: reports.filter((r: any) => !r.deletedAt).length,
        crawl_log_count: logs.length,
        competitor_names: comps.filter((c: any) => !c.deletedAt).map((c: any) => c.name),
        report_titles: reports.filter((r: any) => !r.deletedAt).map((r: any) => r.title),
        event_trend: buildDaily(events, 30),
        crawl_success_count: logs.filter((l: any) => l.status === "success").length,
        crawl_fail_count: logs.filter((l: any) => l.status === "failed").length,
      });
    },
  },
  {
    url: "/api/admin/users/:id",
    method: "put",
    timeout: 200,
    response: ({ headers, url, body }: any) => {
      const a = requireAdminOrErr(headers);
      if (a!.err) return a!.err;
      const d = db();
      const id = idFrom(url);
      const u = d.users.find((x: any) => x.id === id);
      if (!u) return err(40402, "用户不存在");
      const patch = body || {};
      if (patch.username !== undefined) {
        const username = (patch.username ?? "").trim();
        if (!username) return err(40002, "账号名不能为空");
        if (!USERNAME_RE.test(username)) return err(40013, "账号名需 3-30 位，仅字母/数字/下划线/中划线");
        const v = username.toLowerCase();
        const clash = d.users.some(
          (x: any) => x.id !== id && ((x.username || "").toLowerCase() === v || (x.email || "").toLowerCase() === v),
        );
        if (clash) return err(40011, "该账号名已被占用");
        u.username = username;
      }
      if (patch.is_admin !== undefined) u.isAdmin = !!patch.is_admin;
      if (patch.is_active !== undefined) u.active = !!patch.is_active;
      if (patch.new_password !== undefined && patch.new_password !== "") {
        if ((patch.new_password || "").length < 6) return err(40011, "新密码至少 6 位");
        u.password = patch.new_password;
      }
      logAudit(d, a!.admin, "update_user", "user", id, `修改用户 ${u.username} 的资料`);
      return ok(adminUser(u));
    },
  },
  {
    url: "/api/admin/users/:id",
    method: "delete",
    timeout: 200,
    response: ({ headers, url }: any) => {
      const a = requireAdminOrErr(headers);
      if (a!.err) return a!.err;
      const d = db();
      const id = idFrom(url);
      const idx = d.users.findIndex((x: any) => x.id === id);
      if (idx < 0) return err(40402, "用户不存在");
      const target = d.users[idx];
      // 连同名下竞品、情报事件、报告、抓取日志一并清理
      const compIds = new Set(d.competitors.filter((c: any) => c.userId === id).map((c: any) => c.id));
      d.competitors = d.competitors.filter((c: any) => c.userId !== id);
      d.events = d.events.filter((e: any) => !compIds.has(e.competitorId));
      d.reports = d.reports.filter((r: any) => r.userId !== id);
      d.crawlLogs = d.crawlLogs.filter((l: any) => l.userId !== id);
      d.users.splice(idx, 1);
      logAudit(d, a!.admin, "delete_user", "user", id, `删除用户 ${target.username}`);
      return ok(null);
    },
  },

  // ---------------- 全部竞品 ----------------
  {
    url: "/api/admin/competitors",
    method: "get",
    timeout: 200,
    response: ({ headers, query }: any) => {
      const g = guard(headers);
      if (g) return g;
      const d = db();
      const keyword = ((query?.keyword || "") as string).trim().toLowerCase();
      const userById: Record<number, any> = Object.fromEntries(d.users.map((u: any) => [u.id, u]));
      const list = d.competitors
        .filter((c: any) => !c.deletedAt)
        .filter(
          (c: any) =>
            !keyword ||
            (c.name || "").toLowerCase().includes(keyword) ||
            (c.officialUrl || "").toLowerCase().includes(keyword),
        )
        .map((c: any) => {
          const owner = userById[c.userId];
          return {
            ...serializeCompetitor(c),
            ownerUsername: owner?.username ?? "",
            ownerNickname: owner?.name ?? "",
          };
        });
      return ok(pageSlice(list, query?.page, query?.page_size));
    },
  },
  {
    // 注意：content-type 为 multipart/form-data，vite-plugin-mock 不解析文件内容，
    // 这里只回填一个托管地址并同步同域名竞品的 logoUrl，模拟后端行为
    url: "/api/admin/competitors/:id/icon",
    method: "post",
    timeout: 300,
    response: ({ headers, url }: any) => {
      const a = requireAdminOrErr(headers);
      if (a!.err) return a!.err;
      const d = db();
      const id = idFrom(url);
      const c = d.competitors.find((x: any) => x.id === id && !x.deletedAt);
      if (!c) return err(40401, "竞品不存在");
      const logoUrl = `/api/icons/mock-${id}.png`;
      const host = cleanHost(c.officialUrl);
      d.competitors.forEach((x: any) => {
        if (!x.deletedAt && cleanHost(x.officialUrl) === host) x.logoUrl = logoUrl;
      });
      logAudit(d, a!.admin, "upload_competitor_icon", "competitor", id, `上传竞品 ${c.name} 的图标`);
      return ok({ logoUrl });
    },
  },
  {
    url: "/api/admin/competitors/:id/refresh-icon",
    method: "post",
    timeout: 500,
    response: ({ headers, url }: any) => {
      const a = requireAdminOrErr(headers);
      if (a!.err) return a!.err;
      const d = db();
      const id = idFrom(url);
      const c = d.competitors.find((x: any) => x.id === id && !x.deletedAt);
      if (!c) return err(40401, "竞品不存在");
      const logoUrl = `/api/icons/mock-${id}.png`;
      const host = cleanHost(c.officialUrl);
      d.competitors.forEach((x: any) => {
        if (!x.deletedAt && cleanHost(x.officialUrl) === host) x.logoUrl = logoUrl;
      });
      logAudit(d, a!.admin, "refresh_competitor_icon", "competitor", id, `刷新竞品 ${c.name} 的图标`);
      return ok({ logoUrl });
    },
  },

  // ---------------- 平台数据（三 tab） ----------------
  {
    url: "/api/admin/events",
    method: "get",
    timeout: 200,
    response: ({ headers, query }: any) => {
      const g = guard(headers);
      if (g) return g;
      const d = db();
      const keyword = ((query?.keyword || "") as string).trim().toLowerCase();
      const list = d.events
        .map((e: any) => {
          const c = d.competitors.find((x: any) => x.id === e.competitorId);
          const owner = c ? d.users.find((x: any) => x.id === c.userId) : null;
          return {
            id: e.id,
            title: e.title,
            event_type: e.eventType,
            event_type_label: EVENT_TYPES[e.eventType]?.label ?? e.eventType,
            priority: e.priority,
            competitor_name: c ? c.name : "",
            owner_username: owner ? owner.username : "",
            created_at: formatDateTime(e.createdAt),
          };
        })
        .filter((x: any) => !keyword || x.title.toLowerCase().includes(keyword) || x.competitor_name.toLowerCase().includes(keyword));
      return ok(pageSlice(list, query?.page, query?.page_size));
    },
  },
  {
    url: "/api/admin/reports",
    method: "get",
    timeout: 200,
    response: ({ headers, query }: any) => {
      const g = guard(headers);
      if (g) return g;
      const d = db();
      const keyword = ((query?.keyword || "") as string).trim().toLowerCase();
      const includeDeleted = query?.include_deleted === "true" || query?.include_deleted === true;
      const list = d.reports
        .filter((r: any) => includeDeleted || !r.deletedAt)
        .filter((r: any) => !keyword || (r.title || "").toLowerCase().includes(keyword))
        .map((r: any) => ({
          id: r.id,
          title: r.title,
          report_type: r.type,
          range_start: r.rangeStart,
          range_end: r.rangeEnd,
          competitor_count: r.competitors,
          event_count: (r.stats || []).find((s: any) => s.key === "events")?.value ?? 0,
          owner_username: ownerName(d, r.userId),
          created_at: r.generatedAt,
          deleted: !!r.deletedAt,
        }));
      return ok(pageSlice(list, query?.page, query?.page_size));
    },
  },
  {
    url: "/api/admin/crawl-logs",
    method: "get",
    timeout: 200,
    response: ({ headers, query }: any) => {
      const g = guard(headers);
      if (g) return g;
      const d = db();
      const keyword = ((query?.keyword || "") as string).trim().toLowerCase();
      const list = d.crawlLogs
        .map((l: any) => ({
          id: l.id,
          competitor_name: l.competitorName,
          source_name: l.sourceName,
          status: l.status,
          trigger: l.trigger,
          changed: l.changed,
          event_created: l.eventCreated,
          duration_ms: l.durationMs,
          owner_username: ownerName(d, l.userId),
          created_at: formatDateTime(l.createdAt),
        }))
        .filter(
          (x: any) =>
            !keyword ||
            (x.competitor_name || "").toLowerCase().includes(keyword) ||
            (x.source_name || "").toLowerCase().includes(keyword),
        );
      return ok(pageSlice(list, query?.page, query?.page_size));
    },
  },

  // ---------------- 审计日志 ----------------
  {
    url: "/api/admin/audit-logs",
    method: "get",
    timeout: 200,
    response: ({ headers, query }: any) => {
      const g = guard(headers);
      if (g) return g;
      const d = db();
      const action = ((query?.action || "") as string).trim();
      const keyword = ((query?.keyword || "") as string).trim().toLowerCase();
      const list = d.auditLogs
        .filter((a: any) => !action || a.action === action)
        .filter(
          (a: any) =>
            !keyword ||
            [a.adminUsername, a.targetType, a.detail].join(" ").toLowerCase().includes(keyword),
        )
        .map(auditOut);
      return ok(pageSlice(list, query?.page, query?.page_size));
    },
  },

  // ---------------- 平台公告 ----------------
  {
    url: "/api/admin/announcements",
    method: "get",
    timeout: 200,
    response: ({ headers }: any) => {
      const g = guard(headers);
      if (g) return g;
      return ok(
        db()
          .announcements.slice()
          .sort((a: any, b: any) => b.id - a.id)
          .map(annOut),
      );
    },
  },
  {
    url: "/api/admin/announcements",
    method: "post",
    timeout: 200,
    response: ({ headers, body }: any) => {
      const a = requireAdminOrErr(headers);
      if (a!.err) return a!.err;
      const d = db();
      const content = ((body?.content || "") as string).trim();
      if (!content) return err(40000, "公告内容不能为空");
      const item = { id: d.seq.announcement++, content, is_active: true, createdAt: new Date().toISOString() };
      d.announcements.unshift(item);
      logAudit(d, a!.admin, "create_announcement", "announcement", item.id, "发布平台公告");
      return ok(annOut(item));
    },
  },
  {
    url: "/api/admin/announcements/:id",
    method: "patch",
    timeout: 200,
    response: ({ headers, url, body }: any) => {
      const a = requireAdminOrErr(headers);
      if (a!.err) return a!.err;
      const d = db();
      const id = idFrom(url);
      const item = d.announcements.find((x: any) => x.id === id);
      if (!item) return err(40403, "公告不存在");
      if (body?.content !== undefined) item.content = body.content.trim();
      if (body?.is_active !== undefined) item.is_active = !!body.is_active;
      logAudit(d, a!.admin, "update_announcement", "announcement", id, "更新平台公告");
      return ok(annOut(item));
    },
  },
  {
    // 任意登录用户可读：顶栏公告横幅用
    url: "/api/announcements/active",
    method: "get",
    timeout: 100,
    response: ({ headers }: any) => {
      const u = authUser(headers);
      if (!u) return err(40100, "未登录或登录已过期");
      return ok(db().announcements.filter((a: any) => a.is_active).map(annOut));
    },
  },
];