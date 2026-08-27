import { useRouter } from "vue-router";
import { useAuthStore } from "@/stores/auth";
import type { LoginRequest, RegisterRequest } from "@/types/auth";

/**
 * 登录业务逻辑 composable
 * - 视图层只负责触发和渲染，业务（请求/token/存储）在 store，跳转在 composable
 * - 失败提示交给 request.ts 拦截器统一弹，这里不再重复 ElMessage
 */
export function useAuth() {
  const router = useRouter();
  const authStore = useAuthStore();

  // 登录
  async function login(req: LoginRequest): Promise<boolean> {
    const ok = await authStore.login(req);
    if (ok) {
        await router.replace({ name: "AppLayout" });
    }
    return ok;
  }

  // 注册
  async function register(req: RegisterRequest): Promise<boolean> {
    const ok = await authStore.register(req);
    if (ok) await router.replace({ name: "AppLayout" });
    return ok;
  }

  return {
    login,
    register,
    loading: authStore.loading,
  };
}
