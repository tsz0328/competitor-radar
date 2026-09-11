import axios, {
  type AxiosInstance,
  type InternalAxiosRequestConfig,
  type AxiosResponse,
} from "axios";
import router from "@/router";
import { ElMessage } from "element-plus";

const request: AxiosInstance = axios.create({
  baseURL: import.meta.env.VITE_API_BASE ?? "", // dev 期留空，兼容 vite-plugin-mock
  timeout: 10000,
});

// 请求拦截器：自动附加 token
request.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    const token = localStorage.getItem("token");
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
        ElMessage.error(body.message || "请求失败");
        return Promise.reject(new Error(body.message || "请求失败"));
      }
      return body.data; // 直接返回业务数据
    }
    return body;
  },
  (error) => {
    const data = error.response?.data;
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

    // 认证类错误：业务码 401xx 都表示需要重新登录
    // 40100 通用未登录 / 40101 账号或密码错误 / 40102 令牌过期 / 40103 用户不存在
    // 用百位段判断，覆盖 40100~40199，也兼容以后新增的 401 子码
    const isAuthError = code !== undefined && Math.floor(code / 100) === 401;
    if (isAuthError) {
      localStorage.removeItem("token");
      ElMessage.error(serverMsg || "登录已过期，请重新登录");
      // 登录/注册接口本身不要跳登录页，避免「正在登录却被踢去登录」
      const url = error.config?.url ?? "";
      if (!url.includes("/auth/login") && !url.includes("/auth/register")) {
        router.push({ name: "Login" });
      }
    } else {
      ElMessage.error(serverMsg || error.message || "网络错误");
    }
    return Promise.reject(error);
  },
);

export default request;
