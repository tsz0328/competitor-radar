import axios, {
  type AxiosInstance,
  type InternalAxiosRequestConfig,
  type AxiosResponse,
} from "axios";
import { ElMessage } from "element-plus";
import { clearAuth, readToken } from "@/utils/authStorage";

const request: AxiosInstance = axios.create({
  baseURL: import.meta.env.VITE_API_BASE ?? "", // dev 期留空，兼容 vite-plugin-mock
  timeout: 10000,
});

/**
 * 需要等待大模型 / 浏览器渲染的"重活"接口专用超时（3 分钟）。
 *
 * 全局 10s 只适合普通增删改查；像"立即抓取"（起浏览器 + 逐页渲染 + LLM 分析）、
 * "生成周报"这类请求会轻松超过 10s，若不单独放宽就会误报
 * "timeout of 10000ms exceeded"（实为前端主动断开，后端其实还在跑）。
 */
export const LONG_REQUEST_TIMEOUT = 180_000;

// HTTP 状态码兜底文案（后端未返回 message 时使用，附带操作引导）
const HTTP_STATUS_HINT: Record<number, string> = {
  400: "请求参数有误，请检查填写内容后重试",
  401: "登录状态已失效，请重新登录",
  403: "没有权限执行此操作，请检查账号权限",
  404: "请求的资源不存在或已被删除，请刷新页面后重试",
  405: "请求方式不被允许，请刷新页面后重试",
  409: "操作冲突，请稍后重试",
  422: "请求参数校验失败，请检查填写内容",
  429: "操作过于频繁，请稍后再试",
  500: "服务器内部错误，请稍后再试",
  502: "服务器网关错误，请稍后再试",
  503: "服务暂时不可用，请稍后再试",
  504: "服务器响应超时，请稍后再试",
};

// 请求拦截器：自动附加 token
// token 可能在 localStorage（记住我）或 sessionStorage（仅本次会话），统一从 utils 读
request.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    const token = readToken();
    if (token) config.headers.Authorization = `Bearer ${token}`;
    return config;
  },
  (error) => Promise.reject(error),
);

// 响应拦截器：统一解包 + 业务错误处理
request.interceptors.response.use(
  (resp: AxiosResponse) => {
    const body = resp.data;
    // 兼容无包装的响应（如个别接口直接返回数组/对象）
    if (body && typeof body === "object" && "code" in body) {
      if (body.code !== 200 && body.code !== 0) {
        const msg = body.message || "请求失败，请稍后重试";
        ElMessage.error(msg);
        return Promise.reject(new Error(msg));
      }
      return body.data; // 直接返回业务数据
    }
    return body;
  },
  async (error) => {
    let data = error.response?.data;
    // 导出类接口（responseType 为 text / blob）出错时，错误体是未解析的字符串或
    // Blob，这里统一还原成 JSON，保证认证类错误（401xx）仍能被识别、正确跳登录。
    if (data instanceof Blob) {
      try {
        data = JSON.parse(await data.text());
      } catch {
        data = undefined;
      }
    } else if (typeof data === "string") {
      try {
        data = JSON.parse(data);
      } catch {
        data = undefined;
      }
    }
    // 后端统一错误壳：{ code, message, data }，优先用后端文案
    const code: number | undefined = data?.code;
    const serverMsg: string | undefined =
      typeof data?.message === "string"
        ? data.message
        : typeof data?.detail === "string"
          ? data.detail
          : Array.isArray(data?.detail)
            ? data.detail[0]?.msg
            : undefined;

    // 友好文案：优先后端 message；没有时按「超时 / 断网 / 状态码」给操作引导，
    // 不再把 axios 的英文原文（如 "Request failed with status code 401"）透给用户
    let friendly = serverMsg ?? "";
    if (!friendly) {
      if (error.code === "ECONNABORTED") {
        friendly = "请求超时，请检查网络后重试（耗时操作可稍候直接查看结果）";
      } else if (!error.response) {
        friendly = "无法连接服务器，请检查网络连接后重试";
      } else if (typeof error.response.status === "number") {
        friendly = HTTP_STATUS_HINT[error.response.status] ?? "请求失败，请稍后重试";
      } else {
        friendly = "请求失败，请稍后重试";
      }
    }

    // 认证类错误：业务码 401xx 都表示需要重新登录
    // 40100 通用未登录 / 40101 账号或密码错误 / 40102 令牌过期 / 40103 用户不存在
    // 用百位段判断，覆盖 40100~40199，也兼容以后新增的 401 子码
    const isAuthError = code !== undefined && Math.floor(code / 100) === 401;
    if (isAuthError) {
      clearAuth(); // 两个介质都要清，避免残留旧令牌
      ElMessage.error(friendly);
      // 登录/注册接口本身不要跳登录页，避免「正在登录却被踢去登录」
      const url = error.config?.url ?? "";
      if (!url.includes("/auth/login") && !url.includes("/auth/register")) {
        // 整页重载跳登录：清空 Pinia 里上一账号的数据，避免换账号后还看得到旧内容
        window.location.assign("/login");
      }
    } else {
      ElMessage.error(friendly);
    }
    // 用同一份中文文案 reject：视图层 catch 里读 e.message 时不会再拿到英文原文
    return Promise.reject(new Error(friendly));
  },
);

export default request;
