/**
 * 认证相关数据模型
 * 供 API 层、stores、composables、视图层共用
 */

// 登录用户信息（token 解码后的当前用户）
export interface User {
  id: number;
  name: string;
  avatar: string;
}

// 登录请求入参
export interface LoginRequest {
  account: string;
  password: string;
}

// 注册请求入参
export interface RegisterRequest {
  account: string;
  password: string;
}

// 认证成功后的返回（登录 / 注册自动登录：直接返回 token + user）
export interface AuthResult {
  token: string;
  user: User;
}
