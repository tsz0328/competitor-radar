import request from "@/api/request";

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
  username: string;
  email: string;
  /** 是否管理员 */
  is_admin: boolean;
  /** 是否启用（false = 已停用，无法登录） */
  is_active: boolean;
  /** 密码位数（仅长度，不暴露明文）；null 表示未知 */
  password_length: number | null;
}

/** 修改用户入参：只传要改的字段 */
export interface AdminUserUpdate {
  username?: string;
  email?: string;
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
