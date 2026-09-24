import type { AxiosAdapter, AxiosResponse, AxiosRequestConfig } from "axios";
import request from "@/api/request";

/**
 * 浏览器端 mock 适配器（纯前端演示部署用）。
 *
 * vite-plugin-mock@3 只在 dev server 注入 mock（configureServer 钩子），
 * 生产构建时不会把 mock 打进 dist。这里改用 axios 自定义 adapter 在浏览器端
 * 直接接管 /api 请求，好处是能拿到 axios 请求拦截器写进 config.headers 的
 * Authorization（mockjs 客户端劫持 XHR 时拿不到 request header，是死结）。
 *
 * mock 文件（../../mock/*.ts）导出与 vite-plugin-mock 完全一致的 MockMethod[]，
 * 其 response 签名 ({ url, body, query, headers }) 正好能被这里逐字段喂入。
 */

type MockMethod = {
  url: string;
  method?: string;
  timeout?: number;
  response?: (opt: { url: string; body: any; query: any; headers: any }) => any;
  rawResponse?: (req: any, res: any) => void;
};

function parseQuery(url: string): Record<string, any> {
  const q = url.split("?")[1];
  if (!q) return {};
  const out: Record<string, any> = {};
  for (const [k, v] of new URLSearchParams(q)) out[k] = v;
  return out;
}

// 支持 /api/competitors/:id 这类路径参数匹配
function matchUrl(pattern: string, path: string): boolean {
  const p = pattern.split("/").filter(Boolean);
  const u = path.split("/").filter(Boolean);
  if (p.length !== u.length) return false;
  return p.every((seg, i) => seg.startsWith(":") || seg === u[i]);
}

async function loadMethods(): Promise<MockMethod[]> {
  const mods = import.meta.glob("../../mock/*.ts");
  const loaded = await Promise.all(
    Object.values(mods).map((load) => load().then((m: any) => m.default)),
  );
  // db.ts 等工具模块 default 导出非数组，过滤掉；业务 mock 的 default 是 MockMethod[]
  return loaded.filter((d) => Array.isArray(d)).flat() as MockMethod[];
}

function extractAuthHeader(config: AxiosRequestConfig): string {
  const h: any = config.headers;
  if (!h) return "";
  if (typeof h.get === "function") return h.get("Authorization") || "";
  return h.Authorization || h.authorization || "";
}

export async function setupBrowserMock(): Promise<void> {
  const methods = await loadMethods();

  const adapter: AxiosAdapter = async (config: AxiosRequestConfig): Promise<AxiosResponse> => {
    const fullUrl = config.url || "";
    const path = fullUrl.split("?")[0];
    const method = (config.method || "get").toLowerCase();

    const matched = methods.find(
      (m) => (!m.method || m.method.toLowerCase() === method) && matchUrl(m.url, path),
    );

    if (!matched) {
      const data = {
        code: 404,
        message: `演示数据未覆盖该接口：${method.toUpperCase()} ${path}`,
      };
      return { data, status: 200, statusText: "OK", headers: {}, config, request: {} } as AxiosResponse;
    }

    if (matched.timeout) {
      await new Promise((r) => setTimeout(r, matched.timeout));
    }

    let body: any = config.data;
    if (typeof body === "string") {
      try {
        body = JSON.parse(body);
      } catch {
        /* 保持原始字符串 */
      }
    }

    const query = parseQuery(fullUrl);
    // authUser 读取 headers.authorization，这里把 axios 设好的 Bearer token 透传过去
    const headers = { authorization: extractAuthHeader(config) };

    let result: any;
    try {
      result =
        typeof matched.response === "function"
          ? matched.response({ url: path, body, query, headers })
          : matched.response;
    } catch (e) {
      const data = { code: 500, message: `mock 执行出错：${String(e).slice(0, 200)}` };
      return { data, status: 200, statusText: "OK", headers: {}, config, request: {} } as AxiosResponse;
    }

    return { data: result, status: 200, statusText: "OK", headers: {}, config, request: {} } as AxiosResponse;
  };

  request.defaults.adapter = adapter;
}
