import request from "@/api/request";
import type {
  AuthResult,
  CodeLoginRequest,
  EmailCodeScene,
  LoginRequest,
  RefreshRequest,
  RegisterRequest,
  ResetPasswordRequest,
} from "@/types/auth";

export function login(req: LoginRequest): Promise<AuthResult> {
  return request.post<unknown, AuthResult>("/api/auth/login", req);
}

export function register(req: RegisterRequest): Promise<AuthResult> {
  return request.post<unknown, AuthResult>("/api/auth/register", req);
}

/**
 * 发送邮箱验证码（匿名可用）。
 *
 * scene=login：登录 / 注册 / 用户中心绑定邮箱共用，`account` 必须是**邮箱**；
 * scene=reset：重置密码用，`account` 可以是**账号或邮箱**——后端先定位账号，
 * 再把验证码发到该账号绑定的邮箱上。
 *
 * 两个场景在服务端缓存里互相隔离，登录拿到的码不能拿去重置密码。
 */
export function sendEmailCode(
  account: string,
  scene: EmailCodeScene = "login",
): Promise<void> {
  return request.post<unknown, void>("/api/auth/email-code", { account, scene });
}

/** 邮箱验证码登录：该邮箱还没有账号时后端会自动建号（账号名默认就是该邮箱） */
export function loginByCode(req: CodeLoginRequest): Promise<AuthResult> {
  return request.post<unknown, AuthResult>("/api/auth/login-by-code", req);
}

/** 用邮箱验证码重置密码；成功后后端直接返回登录态，省掉一次重复输入 */
export function resetPassword(req: ResetPasswordRequest): Promise<AuthResult> {
  return request.post<unknown, AuthResult>("/api/auth/reset-password", req);
}

/**
 * 令牌续期：用当前仍有效的令牌换发一个新的。
 * 前端在「即将过期」提醒里调用；令牌若已真正过期，后端会以 40102 拒绝并触发强制登出。
 */
export function refreshToken(req: RefreshRequest): Promise<AuthResult> {
  return request.post<unknown, AuthResult>("/api/auth/refresh", req);
}
