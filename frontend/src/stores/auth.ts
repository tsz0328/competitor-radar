import { ref } from "vue";
import { defineStore } from "pinia";
import { login as loginApi, register as registerApi } from "@/api/auth";
import {
  clearAuth,
  readToken,
  readUser,
  saveAuth,
  saveUser,
} from "@/utils/authStorage";
import type { LoginRequest, RegisterRequest, User } from "@/types/auth";

export const useAuthStore = defineStore("auth", () => {
  // 初始值来自存储：勾了「记住我」在 localStorage，没勾在 sessionStorage
  const token = ref<string>(readToken());
  const user = ref<User | null>(readUser());
  const loading = ref(false);
  const error = ref("");

  // 登录
  async function login(req: LoginRequest) {
    loading.value = true;
    error.value = "";
    try {
      const res = await loginApi(req);
      // 「记住我」决定存 localStorage（跨浏览器重启）还是 sessionStorage（仅本次会话）
      saveAuth(res.token, res.user, Boolean(req.remember));
      token.value = res.token;
      user.value = res.user;
      return true;
    } catch (e) {
      error.value = (e as Error).message || "网络错误";
      return false;
    } finally {
      loading.value = false;
    }
  }
  /** 资料更新后同步内存 + 存储：侧边栏的账号/邮箱/头像会立刻跟着变 */
  function setUser(next: User) {
    user.value = next;
    saveUser(next);
  }

  // 退出登录
  function logout() {
    token.value = "";
    user.value = null;
    clearAuth();
    // 整页重载跳登录：竞品/事件/报告等 store 里还留着上一账号的数据，
    // 整页重载是最省事也最彻底的清空方式（避免换账号后短暂看到旧内容）。
    window.location.assign("/login");
  }

  // 注册
  async function register(req: RegisterRequest) {
    loading.value = true;
    error.value = "";
    try {
      const res = await registerApi(req);
      // 注册页没有「记住我」勾选框，按未勾选处理：只保留本次会话的登录态
      saveAuth(res.token, res.user, Boolean(req.remember));
      token.value = res.token;
      user.value = res.user;
      return true;
    } catch (e) {
      error.value = (e as Error).message || "网络错误";
      return false;
    } finally {
      loading.value = false;
    }
  }

  return { token, user, loading, error, login, logout, register, setUser };
});
