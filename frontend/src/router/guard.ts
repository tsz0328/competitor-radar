/**
 * 路由角色守卫的纯函数：按登录角色拦截「不该进的页面」，返回重定向目标。
 *
 * 抽成纯函数的原因：角色判定规则可单测（guard.spec.ts），且与 fetchMyProfile
 * 兜底逻辑（旧会话缺 is_admin 字段）解耦。
 *
 * 约定（与 router/index.ts 的 meta 配套）：
 * - meta.userOnly 的用户业务页：管理员一律不让进（管理员只管用户数据）；
 * - meta.adminOnly 的管理页：普通用户不让进；
 * - 唯一例外：管理员仍可进 `Setting?tab=account`（用户中心），改自己的账号资料。
 */
import type { RouteLocationNormalized } from "vue-router";

export interface RoleRedirect {
  name: string;
}

type GuardTarget = Pick<RouteLocationNormalized, "name" | "meta" | "query">;

export function resolveRoleRedirect(
  to: GuardTarget,
  isAdmin: boolean,
): RoleRedirect | null {
  if (to.meta.adminOnly && !isAdmin) return { name: "Dashboard" };
  if (to.meta.userOnly && isAdmin) {
    if (to.name === "Setting" && to.query.tab === "account") return null;
    return { name: "AdminOverview" };
  }
  return null;
}