import { useRouter } from "vue-router";
import { useAuthStore } from "@/stores/auth";
import type {
  CodeLoginRequest,
  LoginRequest,
  RegisterRequest,
  ResetPasswordRequest,
} from "@/types/auth";

/**
 * 登录业务逻辑 composable
 * - 视图层只负责触发和渲染，业务（请求/token/存储）在 store，跳转在 composable
 * - 失败提示交给 request.ts 拦截器统一弹，这里不再重复 ElMessage
 */
export function useAuth() {
  const router = useRouter();
  const authStore = useAuthStore();

  // 登录成功后统一进主界面；四条入口（密码/注册/验证码/重置）行为一致
  async function enterOnSuccess(ok: boolean): Promise<boolean> {
    if (ok) await router.replace({ name: "AppLayout" });
    return ok;
  }

  /** 密码登录：account 传账号或邮箱 */
  async function login(req: LoginRequest): Promise<boolean> {
    return enterOnSuccess(await authStore.login(req));
  }

  /** 注册（账号必填、邮箱选填；填了邮箱才校验验证码）；注册成功即登录 */
  async function register(req: RegisterRequest): Promise<boolean> {
    return enterOnSuccess(await authStore.register(req));
  }

  /** 邮箱验证码登录（该邮箱没账号时后端自动建号） */
  async function loginByCode(req: CodeLoginRequest): Promise<boolean> {
    return enterOnSuccess(await authStore.loginByCode(req));
  }

  /** 用邮箱验证码重置密码；成功后后端已签发令牌，直接进主界面 */
  async function resetPassword(req: ResetPasswordRequest): Promise<boolean> {
    return enterOnSuccess(await authStore.resetPassword(req));
  }

  return {
    login,
    register,
    loginByCode,
    resetPassword,
    loading: authStore.loading,
  };
}
