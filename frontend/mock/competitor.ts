import {
  SOURCE_TYPES,
  authUser,
  cleanHost,
  db,
  err,
  idFrom,
  ok,
  serializeCompetitor,
  serializeSource,
  sourceLabel,
} from "./db";

function requireUser(headers: any) {
  const u = authUser(headers);
  if (!u) return null;
  return u;
}

/** 当前用户自己的竞品（忽略回收站） */
function findOwned(d: any, uid: number, id: number) {
  return d.competitors.find((x) => x.id === id && x.userId === uid && !x.deletedAt);
}
/** 当前用户回收站里的竞品 */
function findOwnedTrash(d: any, uid: number, id: number) {
  return d.competitors.find((x) => x.id === id && x.userId === uid && x.deletedAt);
}

function normBase(url: string): string {
  let v = (url || "").trim().replace(/\/+$/, "");
  if (v && !/^https?:\/\//i.test(v)) v = "https://" + v;
  return v;
}

/** 创建/编辑时按 payload 组装监控源 */
function buildSources(d: any, competitorId: number, officialUrl: string, sources?: any[]) {
  const d0 = db();
  const list = sources && sources.length ? sources : [{ sourceType: "homepage" }];
  return list.map((s: any) => {
    const cfg = SOURCE_TYPES.find((t) => t.type === s.sourceType);
    const type = cfg ? s.sourceType : "homepage";
    const url = s.url ? normBase(s.url) : officialUrl;
    return {
      id: d0.seq.source++,
      competitorId,
      sourceType: type,
      name: s.name ?? sourceLabel(type),
      url,
      renderMode: cfg ? cfg.render : "http",
      intervalMinutes: s.intervalMinutes ?? (cfg ? cfg.defaultIntervalMinutes : 1440),
      enabled: true,
      lastStatus: null,
      lastError: null,
      failCount: 0,
      lastCrawledAt: null,
    };
  });
}

export default [
  {
    url: "/api/source-types",
    method: "get",
    timeout: 100,
    response: () => ok(SOURCE_TYPES.map((t) => ({ ...t }))),
  },
  {
    url: "/api/competitors",
    method: "get",
    timeout: 200,
    response: ({ headers }: any) => {
      const u = requireUser(headers);
      if (!u) return err(40100, "未登录或登录已过期");
      const d = db();
      return ok(
        d.competitors
          .filter((c) => c.userId === u.id && !c.deletedAt)
          .map(serializeCompetitor),
      );
    },
  },
  {
    url: "/api/competitors/check-url",
    method: "post",
    timeout: 500,
    response: ({ body }: any) => {
      const url = normBase(body?.url || "");
      if (!url) return ok({ url: "", ok: false, httpStatus: null, message: "网址为空" });
      return ok({ url, ok: true, httpStatus: 200, message: "网址可达" });
    },
  },
  {
    url: "/api/competitors/discover-sources",
    method: "post",
    timeout: 800,
    response: ({ body }: any) => {
      const officialUrl = normBase(body?.officialUrl || "");
      const skip = new Set(body?.skipTypes || []);
      const host = cleanHost(officialUrl);
      const found = (type: string, path: string, origin: string) => ({
        sourceType: type,
        label: sourceLabel(type),
        url: path ? `${officialUrl.replace(/\/+$/, "")}${path}` : null,
        found: !!path,
        origin,
        httpStatus: path ? 200 : null,
      });
      const sources = [
        found("pricing", "/pricing", "common"),
        found("changelog", "/changelog", "common"),
        found("blog", "/blog", "common"),
        found("docs", "/docs", "common"),
        found("status", host ? "" : "", "common"),
        found("rss", "", "common"),
        found("app_store", "", "common"),
      ].filter((s) => !skip.has(s.sourceType) && s.sourceType !== "homepage") as any[];
      return ok({ officialUrl, homepageReachable: !!host, sources });
    },
  },
  {
    url: "/api/competitors/suggest",
    method: "post",
    timeout: 600,
    response: ({ body }: any) => {
      const name = (body?.name ?? "").trim();
      const KNOWN: Record<string, [string, string]> = {
        notion: ["https://www.notion.so", "SaaS工具"],
        feishu: ["https://www.feishu.cn", "SaaS工具"],
        "飞书": ["https://www.feishu.cn", "SaaS工具"],
        chatgpt: ["https://chat.openai.com", "AI产品"],
        openai: ["https://openai.com", "AI产品"],
        canva: ["https://www.canva.com", "SaaS工具"],
        figma: ["https://www.figma.com", "设计工具"],
        keep: ["https://www.keep.com", "运动健身"],
      };
      const hit = KNOWN[name.toLowerCase()];
      if (hit) return ok({ officialUrl: hit[0], category: hit[1], source: "probe", message: "已根据域名探测识别到官网与分类" });
      return ok({ officialUrl: null, category: null, source: "none", message: "未能自动识别：未命中已知品牌库，常见域名探测也未确认到官网，请核对名称拼写后手动填写官网地址" });
    },
  },
  {
    url: "/api/competitors/favicon",
    method: "get",
    timeout: 300,
    response: () => ok({ logoUrl: null }),
  },
  {
    url: "/api/competitors/trash",
    method: "get",
    timeout: 200,
    response: ({ headers }: any) => {
      const u = requireUser(headers);
      if (!u) return err(40100, "未登录或登录已过期");
      const d = db();
      return ok(d.competitors.filter((c) => c.userId === u.id && c.deletedAt).map(serializeCompetitor));
    },
  },
  {
    url: "/api/competitors",
    method: "post",
    timeout: 300,
    response: ({ headers, body }: any) => {
      const u = requireUser(headers);
      if (!u) return err(40100, "未登录或登录已过期");
      const d = db();
      const name = (body?.name ?? "").trim();
      const officialUrl = normBase(body?.officialUrl || "");
      if (!name) return err(40000, "竞品名称不能为空");
      if (!officialUrl) return err(40000, "官网地址不能为空");
      const host = cleanHost(officialUrl);

      // 命中当前用户回收站里的同竞品 → 恢复（restored=true）
      const existing = d.competitors.find((c) => c.userId === u.id && c.deletedAt && cleanHost(c.officialUrl) === host);
      if (existing) {
        existing.deletedAt = null;
        existing.restored = true;
        existing.name = name;
        return ok(serializeCompetitor(existing));
      }

      const id = d.seq.competitor++;
      const sources = buildSources(d, id, officialUrl, body?.sources);
      const row = {
        id,
        userId: u.id,
        name,
        officialUrl,
        category: body?.category || "SaaS工具",
        categoryType: "saas",
        status: "active",
        createdAt: new Date().toISOString(),
        deletedAt: null,
        restored: false,
        logoUrl: "",
        changes: 0,
        todayChanges: 0,
        sources,
      };
      d.competitors.push(row);
      return ok(serializeCompetitor(row));
    },
  },
  {
    url: "/api/competitors/:id",
    method: "patch",
    timeout: 300,
    response: ({ headers, body, url }: any) => {
      const u = requireUser(headers);
      if (!u) return err(40100, "未登录或登录已过期");
      const d = db();
      const id = idFrom(url);
      const c = findOwned(d, u.id, id);
      if (!c) return err(40401, "竞品不存在");
      if (body?.name) c.name = body.name.trim();
      if (body?.officialUrl) c.officialUrl = normBase(body.officialUrl);
      if (body?.category) c.category = body.category;
      if (body?.status) c.status = body.status; // active | paused
      if (body?.sources) c.sources = buildSources(d, id, c.officialUrl, body.sources);
      return ok(serializeCompetitor(c));
    },
  },
  {
    url: "/api/competitors/:id",
    method: "delete",
    timeout: 300,
    response: ({ headers, url }: any) => {
      const u = requireUser(headers);
      if (!u) return err(40100, "未登录或登录已过期");
      const d = db();
      const id = idFrom(url);
      const c = findOwned(d, u.id, id);
      if (!c) return err(40401, "竞品不存在");
      c.deletedAt = new Date().toISOString();
      return ok(null);
    },
  },
  {
    url: "/api/competitors/:id/crawl",
    method: "post",
    timeout: 1500,
    response: ({ headers, url }: any) => {
      const u = requireUser(headers);
      if (!u) return err(40100, "未登录或登录已过期");
      const d = db();
      const id = idFrom(url);
      const c = findOwned(d, u.id, id);
      if (!c) return err(40401, "竞品不存在");
      const enabled = c.sources.filter((s: any) => s.enabled);
      if (!enabled.length) return err(40003, "该竞品没有启用的监控页面");

      const results = enabled.map((s: any, i: number) => {
        const firstTime = !s.lastCrawledAt;
        const failed = s.lastStatus === "failed";
        const changed = !failed && i === 0;
        return {
          sourceId: s.id,
          sourceName: s.name,
          sourceType: s.sourceType,
          status: failed ? "failed" : "success",
          httpStatus: failed ? 504 : 200,
          changed,
          firstTime,
          eventCreated: changed,
          error: failed ? (s.lastError || "抓取失败") : null,
          durationMs: 800 + i * 120,
        };
      });

      const succeeded = results.filter((r: any) => r.status === "success").length;
      const failedCount = results.filter((r: any) => r.status === "failed").length;
      const changedCount = results.filter((r: any) => r.changed).length;

      // 落库：更新源状态 + 竞品变化计数 + 新增一条抓取日志
      enabled.forEach((s: any, i: number) => {
        s.lastCrawledAt = new Date().toISOString();
        s.lastStatus = results[i].status;
        s.failCount = results[i].status === "failed" ? (s.failCount || 0) + 1 : 0;
      });
      if (changedCount) {
        c.changes = (c.changes || 0) + changedCount;
        c.todayChanges = (c.todayChanges || 0) + changedCount;
        const eventId = d.seq.event++;
        d.events.unshift({
          id: eventId,
          competitorId: c.id,
          eventType: "content_update",
          title: `${c.name} 页面检测到新变化`,
          summary: `通过本次抓取在 ${c.name} 官网检测到内容更新。`,
          aiAnalysis: null,
          keywords: [c.name],
          confidence: 0.8,
          priority: "mid",
          createdAt: new Date().toISOString(),
          sourceName: enabled[0].name,
          diffDetail: null,
          sourceUrl: c.officialUrl,
        });
      }
      d.crawlLogs.unshift({
        id: d.seq.crawlLog++,
        userId: u.id,
        competitorId: c.id,
        competitorName: c.name,
        sourceId: enabled[0].id,
        sourceName: enabled[0].name,
        sourceType: enabled[0].sourceType,
        url: enabled[0].url,
        trigger: "manual",
        status: results[0].status,
        httpStatus: results[0].httpStatus,
        changed: results[0].changed,
        firstTime: results[0].firstTime,
        eventCreated: results[0].eventCreated,
        durationMs: results[0].durationMs,
        error: results[0].error,
        createdAt: new Date().toISOString(),
      });

      return ok({
        competitorId: c.id,
        total: results.length,
        succeeded,
        failed: failedCount,
        changed: changedCount,
        results,
      });
    },
  },
  {
    url: "/api/competitors/:id/revive-sources",
    method: "post",
    timeout: 300,
    response: ({ headers, url }: any) => {
      const u = requireUser(headers);
      if (!u) return err(40100, "未登录或登录已过期");
      const d = db();
      const id = idFrom(url);
      const c = findOwned(d, u.id, id);
      if (!c) return err(40401, "竞品不存在");
      c.sources.forEach((s: any) => {
        if (!s.enabled) {
          s.enabled = true;
          s.failCount = 0;
        }
      });
      return ok(serializeCompetitor(c));
    },
  },
  {
    url: "/api/competitors/trash/:id",
    method: "post",
    timeout: 300,
    response: ({ headers, url }: any) => {
      const u = requireUser(headers);
      if (!u) return err(40100, "未登录或登录已过期");
      const d = db();
      const id = idFrom(url);
      const c = findOwnedTrash(d, u.id, id);
      if (!c) return err(40401, "竞品不在回收站中");
      c.deletedAt = null;
      c.restored = true;
      return ok(serializeCompetitor(c));
    },
  },
  {
    url: "/api/competitors/trash/:id",
    method: "delete",
    timeout: 300,
    response: ({ headers, url }: any) => {
      const u = requireUser(headers);
      if (!u) return err(40100, "未登录或登录已过期");
      const d = db();
      const id = idFrom(url);
      const idx = d.competitors.findIndex((x) => x.id === id && x.userId === u.id && x.deletedAt);
      if (idx < 0) return err(40401, "竞品不在回收站中");
      d.competitors.splice(idx, 1);
      return ok(null);
    },
  },
];