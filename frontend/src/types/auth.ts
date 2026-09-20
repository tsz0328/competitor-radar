/**
 * 认证相关数据模型
 * 供 API 层、stores、composables、视图层共用
 */

// 登录用户信息（token 解码后的当前用户）
export interface User {
  id: number;
  /** 展示用昵称；没单独设置过时等于账号（用户中心里「昵称」默认取账号） */
  name: string;
  /** 登录账号，全局唯一 */
  username: string;
  /** 头像 data URL，空串表示用首字母占位头像 */
  avatar: string;
  /** 接收通知的邮箱（用户中心里设置），空串表示未设置 */
  email: string;
  /** 是否管理员：可访问系统级设置（发件邮箱等） */
  is_admin?: boolean;
}

// 登录请求入参
export interface LoginRequest {
  account: string;
  password: string;
  /** 「记住我」：勾选后登录态存 localStorage 并由后端签发长期令牌 */
  remember?: boolean;
}

// 注册请求入参
export interface RegisterRequest {
  account: string;
  password: string;
  /** 「记住我」：注册即登录，语义同登录页（注册表单暂无勾选框，默认 false） */
  remember?: boolean;
}

// 认证成功后的返回（登录 / 注册自动登录：直接返回 token + user）
export interface AuthResult {
  token: string;
  user: User;
}
