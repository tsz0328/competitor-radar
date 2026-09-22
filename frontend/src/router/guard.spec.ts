import { describe, expect, it } from "vitest";
import type { LocationQuery } from "vue-router";
import { resolveRoleRedirect } from "@/router/guard";

/** 构造守卫入参：只需要 name / meta / query 三个字段（GuardTarget 是 Pick 类型） */
function target(
  name: string,
  meta: Record<string, unknown>,
  query: LocationQuery = {},
) {
  return { name, meta, query };
}

describe("resolveRoleRedirect 角色守卫", () => {
  it("普通用户访问管理页 → 重定向工作台", () => {
    const to = target("UserManage", { adminOnly: true });
    expect(resolveRoleRedirect(to, false)).toEqual({ name: "Dashboard" });
  });

  it("管理员访问管理页 → 放行", () => {
    const to = target("AdminOverview", { adminOnly: true });
    expect(resolveRoleRedirect(to, true)).toBeNull();
  });

  it("管理员访问用户业务页 → 重定向平台总览", () => {
    const to = target("Dashboard", { userOnly: true });
    expect(resolveRoleRedirect(to, true)).toEqual({ name: "AdminOverview" });
  });

  it("普通用户访问用户业务页 → 放行", () => {
    const to = target("Competitor", { userOnly: true });
    expect(resolveRoleRedirect(to, false)).toBeNull();
  });

  it("管理员访问用户中心（Setting?tab=account）→ 例外放行", () => {
    const to = target("Setting", { userOnly: true }, { tab: "account" });
    expect(resolveRoleRedirect(to, true)).toBeNull();
  });

  it("管理员访问不带 account 的 Setting → 重定向平台总览", () => {
    const to = target("Setting", { userOnly: true });
    expect(resolveRoleRedirect(to, true)).toEqual({ name: "AdminOverview" });
  });

  it("无角色 meta 的页面 → 不做角色拦截", () => {
    const to = target("Landing", {});
    expect(resolveRoleRedirect(to, true)).toBeNull();
    expect(resolveRoleRedirect(to, false)).toBeNull();
  });
});