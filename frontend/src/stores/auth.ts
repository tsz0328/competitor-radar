import { ref } from "vue";
import { defineStore } from "pinia";
import {
  login as loginApi,
  loginByCode as loginByCodeApi,
  register as registerApi,
  resetPassword as resetPasswordApi,
  refreshToken as refreshTokenApi,
} from "@/api/auth";
import {
  clearAuth,
  readToken,
  readUser,
  saveAuth,
  saveUser,
} from "@/utils/authStorage";
import type {
  AuthResult,
  CodeLoginRequest,
  LoginRequest,
  RegisterRequest,
  ResetPasswordRequest,
  User,
} from "@/types/auth";

/** 需要「记住我」语义的入口（注册 / 验证码登录 / 重置密码）统一走这个默认值 */
const REMEMBER_DEFAULT = false;

export const useAuthStore = defineStore("auth", () => {
  // 初始值来自存储：勾了「记住我」在 localStorage，没勾在 sessionStorage
  const token = ref<string>(readToken());
  const user = ref<User | null>(readUser());
  const loading = ref(false);
  const error = ref("");

  /**
   * 登录成功的公共收尾：存 token + user，并更新内存状态。
   * 「记住我」决定存 localStorage（跨浏览器重启）还是 sessionStorage（仅本次会话）。
   */
  function acceptAuth(res: AuthResult, remember: boolean) {
    saveAuth(res.token, res.user, remember);
    token.value = res.token;
    user.value = res.user;
  }

  /** loading / error 的统一包裹：三个登录入口写法保持一致，避免漏改其中一个 */
  async function withLoading(action: () => Promise<void>): Promise<boolean> {
    loading.value = true;
    error.value = "";
    try {
      await action();
      return true;
    } catch (e) {
      error.value = (e as Error).message || "网络错误";
      return false;
    } finally {
      loading.value = false;
    }
  }

  // 邮箱 + 密码登录
  function login(req: LoginRequest) {
    return withLoading(async () => {
      acceptAuth(await loginApi(req), Boolean(req.remember));
    });
  }

  // 注册（注册页没有「记住我」勾选框 → 只保留本次会话的登录态）
  function register(req: RegisterRequest) {
    return withLoading(async () => {
      acceptAuth(await registerApi(req), Boolean(req.remember));
    });
  }

  /**
   * 邮箱验证码登录：该邮箱还没注册过时，后端会自动建一个无密码账号。
   * 新账号未设密码，后续想用密码登录可在用户中心补设。
   */
  function loginByCode(req: CodeLoginRequest) {
    return withLoading(async () => {
      acceptAuth(await loginByCodeApi(req), Boolean(req.remember));
    });
  }

  /** 用验证码重置密码：后端重置成功即视为已登录，直接接住登录态 */
  function resetPassword(req: ResetPasswordRequest) {
    return withLoading(async () => {
      acceptAuth(await resetPasswordApi(req), REMEMBER_DEFAULT);
    });
  }

  /** 资料更新后同步内存 + 存储：侧边栏的账号/邮箱/头像会立刻跟着变 */
  function setUser(next: User) {
    user.value = next;
    saveUser(next);
  }

  /**
   * 令牌续期：用当前仍有效的令牌换发新的，成功后无缝替换登录态、延长到期时间。
   * 不套 withLoading：这是后台静默动作，不该让页面出现 loading。
   * 若令牌已真正过期，refreshToken 会 401，由请求拦截器统一清 token + 跳登录。
   */
  async function renewSession(remember: boolean) {
    acceptAuth(await refreshTokenApi({ remember }), remember);
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

  return {
    token,
    user,
    loading,
    error,
    login,
    logout,
    register,
    loginByCode,
    resetPassword,
    setUser,
    renewSession,
  };
});
