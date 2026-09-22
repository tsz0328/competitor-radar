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
  /** 注册时间（后端已按本地时区格式化好的字符串；空串 = 从未注册） */
  created_at: string;
  /** 最近活跃时间（格式化的字符串；空串 = 从未登录） */
  last_login_at: string;
  /** 密码位数（仅长度，不暴露明文）；null 表示未设置密码（只能用验证码登录） */
  password_length: number | null;
  /** 名下未删除竞品数 */
  competitor_count: number;
  /** 其竞品产出的情报事件数（历史留痕，竞品软删后仍计入） */
  event_count: number;
  /** 名下未删除周报数 */
  report_count: number;
  /** 抓取日志数 */
  crawl_log_count: number;
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

/** 分页响应壳：列表接口统一返回 { items, total } */
export interface AdminUserPage {
  items: AdminUser[];
  total: number;
}

/** 读取用户列表（仅管理员）。keyword 可选，按账号或邮箱模糊匹配；分页必传 */
export function listAdminUsers(params: {
  keyword?: string;
  page: number;
  page_size: number;
}): Promise<AdminUserPage> {
  return request.get<unknown, AdminUserPage>("/api/admin/users", { params });
}

/** 用户详情总览（仅管理员，用于用户管理抽屉） */
export interface UserOverview {
  id: number;
  username: string;
  email: string;
  nickname: string;
  is_admin: boolean;
  is_active: boolean;
  created_at: string;
  last_login_at: string;
  competitor_count: number;
  event_count: number;
  report_count: number;
  crawl_log_count: number;
  /** 名下竞品名列表（供抽屉展示） */
  competitor_names: string[];
  /** 名下报告标题列表（供抽屉展示） */
  report_titles: string[];
  /** 近 30 天产出的情报事件趋势 */
  event_trend: AdminDailyPoint[];
  crawl_success_count: number;
  crawl_fail_count: number;
}

/** 读取用户详情总览（仅管理员） */
export function getUserOverview(id: number): Promise<UserOverview> {
  return request.get<unknown, UserOverview>(`/api/admin/users/${id}/overview`);
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

/** 平台总览：总量卡片数据（竞品/周报只计未删除；事件/抓取日志为全量历史） */
export interface AdminOverviewTotals {
  users: number;
  active_users: number;
  admin_users: number;
  competitors: number;
  sources: number;
  events: number;
  reports: number;
  crawl_logs: number;
}

/** 单日计数点：date 用于 x 轴展示（如 9/15），date_iso 为完整日期 */
export interface AdminDailyPoint {
  date: string;
  date_iso: string;
  count: number;
}

/** 平台总览响应：总量 + 情报/抓取两条近 30 天趋势线 */
export interface AdminOverview {
  totals: AdminOverviewTotals;
  event_trend: AdminDailyPoint[];
  crawl_trend: AdminDailyPoint[];
}

/** 读取平台总览统计（仅管理员） */
export function getAdminOverview(): Promise<AdminOverview> {
  return request.get<unknown, AdminOverview>("/api/admin/overview");
}

/** 管理员重新获取竞品图标（仅管理员）：自动去官网按修复后逻辑解析并沉淀进共享库 */
export function refreshCompetitorIcon(id: number): Promise<{ logoUrl: string }> {
  return request.post<unknown, { logoUrl: string }>(
    `/api/admin/competitors/${id}/refresh-icon`,
  );
}

/** 管理员视角的竞品条目：常规字段 + 归属用户 */
export interface AdminCompetitor extends CompetitorItem {
  /** 归属用户的登录账号 */
  ownerUsername: string;
  /** 归属用户的昵称（为空时界面回退显示账号） */
  ownerNickname: string;
}

/** 分页响应壳：竞品列表 */
export interface AdminCompetitorPage {
  items: AdminCompetitor[];
  total: number;
}

/** 全部用户（未删除）的竞品列表（仅管理员）。keyword 可选，按名称/官网模糊匹配 */
export function listAdminCompetitors(params: {
  keyword?: string;
  page: number;
  page_size: number;
}): Promise<AdminCompetitorPage> {
  return request.get<unknown, AdminCompetitorPage>("/api/admin/competitors", {
    params,
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

/** 发送测试邮件（仅管理员）：成功/失败都返回 200，用 ok / message 表达结果 */
export function testEmail(to: string): Promise<{ ok: boolean; message: string }> {
  return request.post<unknown, { ok: boolean; message: string }>(
    "/api/admin/system-settings/test-email",
    { to },
  );
}

/** 审计日志条目 */
export interface AuditLog {
  id: number;
  admin_username: string;
  action: string;
  target_type: string;
  target_id: number | null;
  detail: string;
  created_at: string;
}

/** 审计日志分页响应壳 */
export interface AuditLogPage {
  items: AuditLog[];
  total: number;
}

/** 读取审计日志（仅管理员）：action / keyword 可选筛选 */
export function listAuditLogs(params: {
  page: number;
  page_size: number;
  action?: string;
  keyword?: string;
}): Promise<AuditLogPage> {
  return request.get<unknown, AuditLogPage>("/api/admin/audit-logs", { params });
}

// ==================== 平台数据（「平台数据」页三 tab） ====================

/** 跨用户情报事件条目（平台数据·情报事件 tab） */
export interface AdminEvent {
  id: number;
  title: string;
  event_type: string;
  event_type_label: string;
  priority: string;
  competitor_name: string;
  owner_username: string;
  created_at: string;
}

/** 跨用户报告条目（平台数据·周度报告 tab） */
export interface AdminReport {
  id: number;
  title: string;
  report_type: string;
  range_start: string;
  range_end: string;
  competitor_count: number;
  event_count: number;
  owner_username: string;
  created_at: string;
  deleted: boolean;
}

/** 跨用户抓取日志条目（平台数据·抓取日志 tab） */
export interface AdminCrawlLog {
  id: number;
  competitor_name: string;
  source_name: string;
  status: string;
  trigger: string;
  changed: boolean;
  event_created: boolean;
  duration_ms: number;
  owner_username: string;
  created_at: string;
}

/** 平台数据列表分页响应的公共壳 */
export interface AdminDataPage<T> {
  items: T[];
  total: number;
}

/** 读取平台数据·情报事件（仅管理员） */
export function listAdminEvents(params: {
  keyword?: string;
  page: number;
  page_size: number;
}): Promise<AdminDataPage<AdminEvent>> {
  return request.get<unknown, AdminDataPage<AdminEvent>>("/api/admin/events", {
    params,
  });
}

/** 读取平台数据·报告（仅管理员，含软删标注） */
export function listAdminReports(params: {
  keyword?: string;
  page: number;
  page_size: number;
  /** true = 一并返回软删（回收站）报告；默认只看未删除的有效报告 */
  include_deleted?: boolean;
}): Promise<AdminDataPage<AdminReport>> {
  return request.get<unknown, AdminDataPage<AdminReport>>("/api/admin/reports", {
    params,
  });
}

/** 读取平台数据·抓取日志（仅管理员） */
export function listAdminCrawlLogs(params: {
  keyword?: string;
  page: number;
  page_size: number;
}): Promise<AdminDataPage<AdminCrawlLog>> {
  return request.get<unknown, AdminDataPage<AdminCrawlLog>>(
    "/api/admin/crawl-logs",
    { params },
  );
}

/** 平台公告（含已下线） */
export interface Announcement {
  id: number;
  content: string;
  is_active: boolean;
  /** ISO 时间字符串 */
  created_at: string;
}

/** 读取全部公告（仅管理员，含已下线） */
export function listAnnouncements(): Promise<Announcement[]> {
  return request.get<unknown, Announcement[]>("/api/admin/announcements");
}

/** 发布公告（仅管理员） */
export function createAnnouncement(content: string): Promise<Announcement> {
  return request.post<unknown, Announcement>("/api/admin/announcements", {
    content,
  });
}

/** 更新公告（仅管理员）：content / is_active 均可选 */
export function updateAnnouncement(
  id: number,
  patch: { content?: string; is_active?: boolean },
): Promise<Announcement> {
  return request.patch<unknown, Announcement>(
    `/api/admin/announcements/${id}`,
    patch,
  );
}

/** 读取当前生效公告（任意登录用户可读，供顶栏横幅） */
export function listActiveAnnouncements(): Promise<Announcement[]> {
  return request.get<unknown, Announcement[]>("/api/announcements/active");
}
