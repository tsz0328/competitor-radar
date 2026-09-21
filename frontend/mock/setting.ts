import { authUser, db, err, idFrom, ok } from "./db";

function requireUser(headers: any) {
  return authUser(headers) || null;
}

// ---------- 序列化 ----------
function previewOf(apiKey: string | undefined): string {
  if (!apiKey) return "";
  return apiKey.length <= 4 ? "****" : `sk-****${apiKey.slice(-4)}`;
}

function providerOut(p: any) {
  return {
    id: p.id,
    name: p.name || "",
    baseUrl: p.baseUrl,
    model: p.model,
    hasApiKey: !!p.hasApiKey,
    apiKeyPreview: p.hasApiKey ? previewOf(p.apiKey) : "",
    isActive: !!p.isActive,
    modelsCount: (p.models || []).length,
  };
}

// ---------- 当前用户的 LLM 数据（与后端按 user_id 隔离一致） ----------
function ownProviders(d: any, uid: number): any[] {
  return d.providers.filter((p: any) => p.userId === uid);
}
function activeProvider(d: any, uid: number): any | null {
  return ownProviders(d, uid).find((p: any) => p.isActive) || null;
}
function getSetting(d: any, uid: number): any {
  let s = d.llmSetting[uid];
  if (!s) {
    s = { enabled: false, timeoutSeconds: 30, minChangeLines: 3, source: "env" };
    d.llmSetting[uid] = s;
  }
  return s;
}
function findOwnedProvider(d: any, uid: number, id: number): any | null {
  return ownProviders(d, uid).find((p: any) => p.id === id) || null;
}
function maxSortOrder(d: any, uid: number): number {
  return ownProviders(d, uid).reduce((m, p) => Math.max(m, p.sortOrder ?? 0), 0);
}

// 开关 + 使用中的供应商 → 展示配置（对齐后端 _compose + _to_out）
function llmOut(d: any, uid: number) {
  const s = getSetting(d, uid);
  const prov = activeProvider(d, uid);
  const apiKey = prov ? prov.apiKey || "" : "";
  const baseUrl = prov ? prov.baseUrl || "" : "";
  const model = prov ? prov.model || "" : "";
  const hasApiKey = !!apiKey;
  const mode = apiKey && baseUrl && model ? "real" : "mock";
  const source = s.source === "database" || prov ? "database" : "env";
  let message: string;
  if (mode === "real") message = `已启用真实模型（${model}）`;
  else if (s.enabled && !apiKey) message = "已开启 AI 分析，但尚未填写 API Key，当前仍走规则 Mock";
  else if (s.enabled) message = "已开启 AI 分析，但配置不完整（缺少地址或模型），当前仍走规则 Mock";
  else message = "未启用 AI 分析，当前走规则 Mock（无需 Key 也能跑通全链路）";
  return {
    enabled: !!s.enabled,
    hasApiKey,
    apiKeyPreview: hasApiKey ? previewOf(apiKey) : "",
    baseUrl,
    model,
    timeoutSeconds: s.timeoutSeconds ?? 30,
    minChangeLines: s.minChangeLines ?? 3,
    mode,
    source,
    message,
  };
}

function statusOut(d: any, uid: number) {
  const l = llmOut(d, uid);
  return {
    mode: l.mode,
    enabled: l.enabled,
    hasApiKey: l.hasApiKey,
    baseUrl: l.baseUrl,
    model: l.model,
    timeoutSeconds: l.timeoutSeconds,
    minChangeLines: l.minChangeLines,
    message:
      l.mode === "real"
        ? `已启用真实模型（${l.model} @ ${l.baseUrl}）`
        : "未配置 Key，使用规则 Mock 兜底（可在「设置」页配置模型）",
  };
}

export default [
  // 静态路由必须排在 :id 之前
  {
    url: "/api/settings/llm",
    method: "get",
    timeout: 200,
    response: ({ headers }: any) => {
      const u = requireUser(headers);
      if (!u) return err(40100, "未登录或登录已过期");
      return ok(llmOut(db(), u.id));
    },
  },
  {
    url: "/api/settings/llm",
    method: "put",
    timeout: 200,
    response: ({ headers, body }: any) => {
      const u = requireUser(headers);
      if (!u) return err(40100, "未登录或登录已过期");
      const d = db();
      const s = getSetting(d, u.id);
      const p = body || {};
      if (p.enabled !== undefined) s.enabled = !!p.enabled;
      if (p.timeoutSeconds !== undefined) s.timeoutSeconds = Number(p.timeoutSeconds) || 30;
      if (p.minChangeLines !== undefined) s.minChangeLines = Number(p.minChangeLines) || 3;
      s.source = "database";
      return ok(llmOut(d, u.id));
    },
  },
  {
    url: "/api/settings/llm/test",
    method: "post",
    timeout: 300,
    response: ({ headers, body }: any) => {
      const u = requireUser(headers);
      if (!u) return err(40100, "未登录或登录已过期");
      const d = db();
      const id = body?.providerId ? Number(body.providerId) : null;
      const prov = id != null ? findOwnedProvider(d, u.id, id) : activeProvider(d, u.id);
      const model = body?.model || prov?.model || "gpt-4o";
      return ok({ ok: true, message: "连接成功，模型可用", model, latencyMs: 120 });
    },
  },
  {
    url: "/api/settings/llm/providers",
    method: "get",
    timeout: 200,
    response: ({ headers }: any) => {
      const u = requireUser(headers);
      if (!u) return err(40100, "未登录或登录已过期");
      const d = db();
      const list = ownProviders(d, u.id).sort((a, b) => (a.sortOrder ?? 0) - (b.sortOrder ?? 0));
      return ok(list.map(providerOut));
    },
  },
  {
    url: "/api/settings/llm/providers",
    method: "post",
    timeout: 300,
    response: ({ headers, body }: any) => {
      const u = requireUser(headers);
      if (!u) return err(40100, "未登录或登录已过期");
      const d = db();
      const baseUrl = (body?.baseUrl || "").trim();
      if (!baseUrl) return err(40002, "baseUrl 不能为空");
      const own = ownProviders(d, u.id);
      const isFirst = own.length === 0;
      const row = {
        id: d.seq.provider++,
        userId: u.id,
        name: body?.name || "",
        baseUrl,
        model: body?.model || "",
        apiKey: body?.apiKey || "",
        hasApiKey: !!(body?.apiKey || (body?.providerId ? true : false)),
        isActive: isFirst || !!body?.isActive,
        sortOrder: maxSortOrder(d, u.id) + 1,
        models: Array.isArray(body?.models) ? body.models : [],
      };
      if (row.isActive) own.forEach((p: any) => (p.isActive = false));
      d.providers.push(row);
      return ok(providerOut(row));
    },
  },
  {
    url: "/api/settings/llm/providers/reorder",
    method: "post",
    timeout: 200,
    response: ({ headers, body }: any) => {
      const u = requireUser(headers);
      if (!u) return err(40100, "未登录或登录已过期");
      const d = db();
      const ids: number[] = Array.isArray(body?.ids) ? body.ids.map(Number) : [];
      const own = ownProviders(d, u.id);
      const map = new Map(own.map((p: any) => [p.id, p]));
      if (ids.some((id) => !map.has(id))) return err(40405, "供应商不存在或已被删除");
      ids.forEach((id, i) => (map.get(id).sortOrder = i));
      return ok(null);
    },
  },
  {
    url: "/api/settings/llm/providers/models",
    method: "post",
    timeout: 300,
    response: ({ headers }: any) => {
      const u = requireUser(headers);
      if (!u) return err(40100, "未登录或登录已过期");
      return ok({ ok: true, models: ["deepseek-chat", "deepseek-reasoner", "gpt-4o-mini", "gpt-4o"], message: "已获取模型列表" });
    },
  },
  {
    url: "/api/llm/status",
    method: "get",
    timeout: 200,
    response: ({ headers }: any) => {
      const u = requireUser(headers);
      if (!u) return err(40100, "未登录或登录已过期");
      return ok(statusOut(db(), u.id));
    },
  },
  {
    url: "/api/settings/llm/providers/:id",
    method: "put",
    timeout: 300,
    response: ({ headers, url, body }: any) => {
      const u = requireUser(headers);
      if (!u) return err(40100, "未登录或登录已过期");
      const d = db();
      const id = idFrom(url);
      const p = findOwnedProvider(d, u.id, id);
      if (!p) return err(40405, "供应商不存在");
      const patch = body || {};
      if (patch.name !== undefined) p.name = patch.name ?? "";
      if (patch.baseUrl !== undefined) p.baseUrl = patch.baseUrl;
      if (patch.model !== undefined) p.model = patch.model;
      if (patch.clearApiKey) {
        p.apiKey = "";
        p.hasApiKey = false;
      } else if (patch.apiKey !== undefined && patch.apiKey !== "") {
        p.apiKey = patch.apiKey;
        p.hasApiKey = true;
      }
      if (Array.isArray(patch.models)) p.models = patch.models;
      return ok(providerOut(p));
    },
  },
  {
    url: "/api/settings/llm/providers/:id",
    method: "delete",
    timeout: 200,
    response: ({ headers, url }: any) => {
      const u = requireUser(headers);
      if (!u) return err(40100, "未登录或登录已过期");
      const d = db();
      const id = idFrom(url);
      const own = ownProviders(d, u.id);
      const idx = own.findIndex((x: any) => x.id === id);
      if (idx < 0) return err(40405, "供应商不存在");
      const wasActive = own[idx].isActive;
      d.providers = d.providers.filter((x: any) => !(x.id === id && x.userId === u.id));
      if (wasActive) {
        const rest = ownProviders(d, u.id).sort((a: any, b: any) => b.id - a.id);
        if (rest.length) rest[0].isActive = true;
      }
      return ok(null);
    },
  },
  {
    url: "/api/settings/llm/providers/:id/activate",
    method: "post",
    timeout: 200,
    response: ({ headers, url }: any) => {
      const u = requireUser(headers);
      if (!u) return err(40100, "未登录或登录已过期");
      const d = db();
      const id = idFrom(url);
      const p = findOwnedProvider(d, u.id, id);
      if (!p) return err(40405, "供应商不存在");
      ownProviders(d, u.id).forEach((x: any) => (x.isActive = x.id === id));
      return ok(providerOut(p));
    },
  },
  {
    url: "/api/settings/llm/providers/:id/duplicate",
    method: "post",
    timeout: 200,
    response: ({ headers, url }: any) => {
      const u = requireUser(headers);
      if (!u) return err(40100, "未登录或登录已过期");
      const d = db();
      const id = idFrom(url);
      const p = findOwnedProvider(d, u.id, id);
      if (!p) return err(40405, "供应商不存在");
      const copy = JSON.parse(JSON.stringify(p));
      copy.id = d.seq.provider++;
      copy.name = copy.name ? `${copy.name} 副本` : "";
      copy.isActive = false;
      copy.sortOrder = maxSortOrder(d, u.id) + 1;
      d.providers.push(copy);
      return ok(providerOut(copy));
    },
  },
  {
    url: "/api/settings/llm/providers/:id/api-key",
    method: "get",
    timeout: 200,
    response: ({ headers, url }: any) => {
      const u = requireUser(headers);
      if (!u) return err(40100, "未登录或登录已过期");
      const d = db();
      const id = idFrom(url);
      const p = findOwnedProvider(d, u.id, id);
      if (!p) return err(40405, "供应商不存在");
      return ok({ apiKey: p.apiKey || "" });
    },
  },
  {
    url: "/api/settings/llm/providers/:id/models",
    method: "get",
    timeout: 200,
    response: ({ headers, url }: any) => {
      const u = requireUser(headers);
      if (!u) return err(40100, "未登录或登录已过期");
      const d = db();
      const id = idFrom(url);
      const p = findOwnedProvider(d, u.id, id);
      if (!p) return err(40405, "供应商不存在");
      return ok({ models: p.models || [] });
    },
  },
];