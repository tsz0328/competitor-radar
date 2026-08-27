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
      if ( body.code !== 200 && body.code !== 0) {
        ElMessage.error(body.message || "请求失败");
        return Promise.reject(new Error(body.message || "请求失败"));
      }
      return body.data; // 直接返回业务数据
    }
    return body;
  },
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem("token");
      ElMessage.error("登录已过期，请重新登录");
      router.push({name: "Login"});
    } else {
      ElMessage.error(error.message || "网络错误");
    }
    return Promise.reject(error);
  },
);

export default request;
