import request from "@/api/request";

/** 用户级偏好（跟着账号走，存在服务端） */
export interface UserPreferences {
  /** 是否允许添加"官网不可达"的竞品 */
  allowUnreachableOfficial: boolean;
  /** 新增竞品时默认勾选的监控页面类型 */
  defaultSourceTypes: string[];
}

/** 读取当前账号的偏好 */
export function fetchMyPreferences(): Promise<UserPreferences> {
  return request.get<unknown, UserPreferences>("/api/users/me/preferences");
}

/** 局部更新偏好：只传要改的字段，其余保持不变 */
export function saveMyPreferences(
  patch: Partial<UserPreferences>,
): Promise<UserPreferences> {
  return request.put<unknown, UserPreferences>("/api/users/me/preferences", patch);
}

/** 用户中心资料：昵称 / 账号 / 接收通知的邮箱 / 头像 */
export interface UserProfile {
  id: number;
  username: string;
  /** 展示用昵称，空串表示未设置（界面回退显示账号） */
  nickname: string;
  /** 接收通知的邮箱，空串表示未设置（回退运维配置的收件人） */
  email: string;
  /** 头像 data URL，空串表示用首字母占位 */
  avatar: string;
  /** 密码位数（仅长度，不暴露明文）；null 表示未知 */
  passwordLength: number | null;
  /** 是否管理员（可访问系统级设置） */
  is_admin: boolean;
}

/** 读取当前账号资料 */
export function fetchMyProfile(): Promise<UserProfile> {
  return request.get<unknown, UserProfile>("/api/users/me");
}

/** 保存账号资料：只传要改的字段 */
export function updateMyProfile(patch: {
  username?: string;
  /** 展示用昵称；传空串表示清除（界面回退显示账号） */
  nickname?: string;
  email?: string;
  avatar?: string;
}): Promise<UserProfile> {
  return request.put<unknown, UserProfile>("/api/users/me", patch);
}

/** 修改密码（必须提供原密码） */
export function changeMyPassword(payload: {
  oldPassword: string;
  newPassword: string;
}): Promise<void> {
  return request.put<unknown, void>("/api/users/me/password", payload);
}
