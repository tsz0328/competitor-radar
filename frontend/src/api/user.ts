import request from "@/api/request";

/** 用户级偏好（跟着账号走，存在服务端） */
export interface UserPreferences {
  /** 是否允许添加"官网不可达"的竞品 */
  allowUnreachableOfficial: boolean;
  /** 新增竞品时默认勾选的监控页面类型 */
  defaultSourceTypes: string[];
  /** 是否接收邮件通知（高优事件 / 抓取变化汇总 / AI 周报）；验证码等账号类邮件不受影响 */
  emailNotifyEnabled: boolean;
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

/** 用户中心资料：昵称 / 账号 / 绑定邮箱 / 头像 */
export interface UserProfile {
  id: number;
  /** 登录账号名（自定义，全局唯一） */
  username: string;
  /** 展示用昵称，空串表示未设置（界面回退显示账号） */
  nickname: string;
  /** 绑定的邮箱；空串表示未绑定（未绑定时不能邮箱登录，也收不到邮件通知） */
  email: string;
  /** 头像 data URL，空串表示用首字母占位 */
  avatar: string;
  /** 密码位数（仅长度，不暴露明文）；null 表示还没设过密码（只能用验证码登录） */
  passwordLength: number | null;
  /** 是否管理员（可访问系统级设置） */
  is_admin: boolean;
}

/** 读取当前账号资料 */
export function fetchMyProfile(): Promise<UserProfile> {
  return request.get<unknown, UserProfile>("/api/users/me");
}

/**
 * 保存账号资料：只传要改的字段（账号 / 昵称 / 头像）。
 *
 * 改账号名不需要验证码——它只是个登录把手；但后端会做「跨列唯一」校验，
 * 不能撞上别人已绑定的邮箱（账号与邮箱共享同一个登录命名空间）。
 *
 * 改邮箱**不在这里**：邮箱是第二登录标识 + 通知收件人 + 找回密码的收件人，
 * 换绑必须先用验证码证明新邮箱归本人所有，走 bindMyEmail。
 */
export function updateMyProfile(patch: {
  username?: string;
  /** 展示用昵称；传空串表示清除（界面回退显示账号） */
  nickname?: string;
  avatar?: string;
}): Promise<UserProfile> {
  return request.put<unknown, UserProfile>("/api/users/me", patch);
}

/**
 * 绑定 / 换绑 / 解绑邮箱。
 *
 * - 传空串 → 解绑（不需要验证码，但账号必须已设密码，否则解绑后就登不进来了）；
 * - 传新邮箱 → 必须带发到该邮箱的验证码（scene=login）。
 *
 * 注册时选了「不填邮箱」的用户，可以在这里补绑，从而拿回邮箱登录与自助找回密码。
 */
export function bindMyEmail(payload: {
  email: string;
  /** 绑定时必填；解绑（email 为空串）时忽略 */
  code?: string;
}): Promise<UserProfile> {
  return request.put<unknown, UserProfile>("/api/users/me/email", payload);
}

/**
 * 修改密码。
 *
 * oldPassword 可空：用邮箱验证码登录自动创建的账号本来就没密码，
 * 这种情况允许直接设置；已有密码的账号仍需传原密码（由后端校验）。
 */
export function changeMyPassword(payload: {
  oldPassword?: string;
  newPassword: string;
}): Promise<void> {
  return request.put<unknown, void>("/api/users/me/password", payload);
}
