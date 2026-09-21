/**
 * 认证相关数据模型
 * 供 API 层、stores、composables、视图层共用
 */

// 登录用户信息（token 解码后的当前用户）
export interface User {
  id: number;
  /** 展示用昵称；没单独设置过时等于账号（用户中心里「昵称」默认取账号） */
  name: string;
  /** 登录账号名（自定义，全局唯一） */
  username: string;
  /** 头像 data URL，空串表示用首字母占位头像 */
  avatar: string;
  /**
   * 绑定的邮箱；**空串表示未绑定**。
   * 它同时是第二登录标识、高优先级情报通知的收件人、自助重置密码的收件人。
   */
  email: string;
  /** 是否管理员：可访问系统级设置（发件邮箱等） */
  is_admin?: boolean;
}

// 登录请求入参
export interface LoginRequest {
  /** 账号名或邮箱，两者都认（后端字段名仍是 account） */
  account: string;
  password: string;
  /** 「记住我」：勾选后登录态存 localStorage 并由后端签发长期令牌 */
  remember?: boolean;
}

// 注册请求入参
export interface RegisterRequest {
  /** 登录账号名：3–30 位，字母/数字/下划线/中划线，禁止 @ */
  username: string;
  password: string;
  /** 邮箱选填；填了就必须带 code（验证码） */
  email?: string;
  /** 邮箱验证码（scene=login）。只有填了邮箱时才需要 */
  code?: string;
  /** 「记住我」：注册即登录，语义同登录页（注册表单暂无勾选框，默认 false） */
  remember?: boolean;
}

/** 邮箱验证码场景：login 用于登录/注册/绑定邮箱，reset 用于重置密码（两者不可混用） */
export type EmailCodeScene = "login" | "reset";

/** 邮箱验证码登录入参（该邮箱还没账号时会自动创建） */
export interface CodeLoginRequest {
  email: string;
  code: string;
  remember?: boolean;
}

/** 用邮箱验证码重置密码入参（account 可以是账号或邮箱） */
export interface ResetPasswordRequest {
  account: string;
  code: string;
  newPassword: string;
}

/** 令牌续期入参：沿用原登录的「记住我」档位，决定新令牌时长 */
export interface RefreshRequest {
  remember?: boolean;
}

// 认证成功后的返回（登录 / 注册自动登录：直接返回 token + user）
export interface AuthResult {
  token: string;
  user: User;
}
