import { ref } from "vue";
import { defineStore } from "pinia";
import { login as loginApi, register as registerApi } from "@/api/auth";
import type { LoginRequest, RegisterRequest, User } from "@/types/auth";

export const useAuthStore = defineStore("auth", () => {
  const token = ref<string>(localStorage.getItem("token") || "");
  const user = ref<User | null>(null);
  const loading = ref(false);
  const error = ref("");

  // 登录
  async function login(req: LoginRequest) {
    loading.value = true;
    error.value = "";
    try {
      const res = await loginApi(req);
      token.value = res.token;
      user.value = res.user;
      localStorage.setItem("token", res.token); // 持久化
      return true;
    } catch (e) {
      error.value = (e as Error).message || "网络错误";
      return false;
    } finally {
      loading.value = false;
    }
  }
  // 退出登录
  function logout() {
    token.value = "";
    user.value = null;
    localStorage.removeItem("token");
  }

  // 注册
  async function register(req: RegisterRequest) {
    loading.value = true;
    error.value = "";
    try {
      const res = await registerApi(req);
      token.value = res.token;
      user.value = res.user;
      localStorage.setItem("token", res.token);
      return true;
    } catch (e) {
      error.value = (e as Error).message || "网络错误";
      return false;
    } finally {
      loading.value = false;
    }
  }

  return { token, user, loading, error, login, logout, register};
});
