import request from "@/api/request";
import type { CompetitorItem } from "@/types/competitor";

/** 系统设置：SMTP 发件配置（五项）。授权码 smtp_password 出于安全不回传，前端始终显示空。 */
export interface SystemSettings {
  smtp_host: string;
  smtp_port: number;
  smtp_username: string;
  smtp_sender: string;
  /** 授权码是否已配置（明文永不回传，仅用于展示"已设置/未设置"） */
  smtp_password_set: boolean;
}

/** 保存系统设置（仅管理员）。
 * - smtp_host / smtp_port / smtp_username / smtp_sender 传空串表示清掉覆盖、回退 .env；
 * - smtp_password 传空串表示"不改动"（保留当前值），只有传非空才更新。 */
export function getSystemSettings(): Promise<SystemSettings> {
  return request.get<unknown, SystemSettings>("/api/admin/system-settings");
}

export function updateSystemSettings(payload: {
  smtp_host?: string;
  smtp_port?: number;
  smtp_username?: string;
  smtp_sender?: string;
  smtp_password?: string;
}): Promise<SystemSettings> {
  return request.put<unknown, SystemSettings>("/api/admin/system-settings", payload);
}

/** 用户管理：列表项（不回传头像，避免响应过大） */
export interface AdminUser {
  id: number;
  /** 登录账号名（自定义，全局唯一） */
  username: string;
  /** 绑定的邮箱；**空串表示未绑定**（未绑定时不能邮箱登录，也收不到邮件通知） */
  email: string;
  /** 是否管理员 */
  is_admin: boolean;
  /** 是否启用（false = 已停用，无法登录） */
  is_active: boolean;
  /** 密码位数（仅长度，不暴露明文）；null 表示未设置密码（只能用验证码登录） */
  password_length: number | null;
}

/**
 * 修改用户入参：只传要改的字段。
 *
 * `username` 是**账号名**（不再是邮箱，两者已解绑），改它只动一列；但后端会做
 * 「跨列唯一」校验——账号名与邮箱共享同一个登录命名空间，不能撞上别人绑定的邮箱。
 *
 * 这里**改不了邮箱**：换绑需要验证码证明新邮箱归属。真要帮用户换，让他在用户中心
 * 自己绑（那边有验证码流程）。
 */
export interface AdminUserUpdate {
  /** 新的登录账号名（3–30 位，字母/数字/下划线/中划线） */
  username?: string;
  is_admin?: boolean;
  is_active?: boolean;
  /** 非空表示重置该用户密码（至少 6 位） */
  new_password?: string;
}

/** 读取用户列表（仅管理员）。keyword 可选，按账号或邮箱模糊匹配 */
export function listAdminUsers(keyword?: string): Promise<AdminUser[]> {
  return request.get<unknown, AdminUser[]>("/api/admin/users", {
    params: keyword ? { keyword } : undefined,
  });
}

/** 修改用户（仅管理员） */
export function updateAdminUser(
  id: number,
  patch: AdminUserUpdate,
): Promise<AdminUser> {
  return request.put<unknown, AdminUser>(`/api/admin/users/${id}`, patch);
}

/** 删除用户（仅管理员）：连同其名下数据一并清理 */
export function deleteAdminUser(id: number): Promise<void> {
  return request.delete<unknown, void>(`/api/admin/users/${id}`);
}

/** 管理员视角的竞品条目：常规字段 + 归属用户 */
export interface AdminCompetitor extends CompetitorItem {
  /** 归属用户的登录账号 */
  ownerUsername: string;
  /** 归属用户的昵称（为空时界面回退显示账号） */
  ownerNickname: string;
}

/** 全部用户（未删除）的竞品列表（仅管理员）。keyword 可选，按名称/官网模糊匹配 */
export function listAdminCompetitors(
  keyword?: string,
): Promise<AdminCompetitor[]> {
  return request.get<unknown, AdminCompetitor[]>("/api/admin/competitors", {
    params: keyword ? { keyword } : undefined,
  });
}

/** 上传/替换竞品图标（仅管理员）：文件走 FormData，multipart 由 axios 自动拼接 */
export function uploadCompetitorIcon(
  id: number,
  file: File,
): Promise<{ logoUrl: string }> {
  const form = new FormData();
  form.append("file", file);
  return request.post<unknown, { logoUrl: string }>(
    `/api/admin/competitors/${id}/icon`,
    form,
  );
}
