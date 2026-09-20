import type { User } from "@/types/auth";

/**
 * 登录态存储：token 与 user 落在 localStorage 还是 sessionStorage。
 *
 * - 勾了「记住我」→ localStorage：关掉浏览器再打开仍是登录态（后端签长期令牌）
 * - 没勾 → sessionStorage：关掉标签页 / 浏览器即失效（后端签会话令牌）
 *
 * 两个介质用同一套键名，读取时 localStorage 优先。同一时刻只会有一份：
 * 每次登录都先 clearAuth() 再写入，不会两边都留着旧令牌。
 */

const TOKEN_KEY = "token";
const USER_KEY = "user";
/** 「记住我」的勾选偏好，只存偏好本身，不含任何凭据 */
const REMEMBER_KEY = "remember";

function parseUser(raw: string | null): User | null {
  if (!raw) return null;
  try {
    return JSON.parse(raw) as User;
  } catch {
    return null;
  }
}

/** 当前登录态落在哪个介质（以 token 为准）；未登录时返回 localStorage */
function activeStore(): Storage {
  if (localStorage.getItem(TOKEN_KEY)) return localStorage;
  if (sessionStorage.getItem(TOKEN_KEY)) return sessionStorage;
  return localStorage;
}

/** 读令牌：请求拦截器与路由守卫都用它，别直接读 localStorage */
export function readToken(): string {
  return (
    localStorage.getItem(TOKEN_KEY) || sessionStorage.getItem(TOKEN_KEY) || ""
  );
}

export function readUser(): User | null {
  return (
    parseUser(localStorage.getItem(USER_KEY)) ??
    parseUser(sessionStorage.getItem(USER_KEY))
  );
}

/** 登录 / 注册成功：按「记住我」选介质，并记下这次的选择供下次预勾 */
export function saveAuth(token: string, user: User, remember: boolean): void {
  clearAuth();
  const store = remember ? localStorage : sessionStorage;
  store.setItem(TOKEN_KEY, token);
  store.setItem(USER_KEY, JSON.stringify(user));
  localStorage.setItem(REMEMBER_KEY, remember ? "1" : "0");
}

/** 资料更新（昵称 / 头像 / 邮箱）：写回当前介质，不影响「记住我」的选择 */
export function saveUser(user: User): void {
  activeStore().setItem(USER_KEY, JSON.stringify(user));
}

/** 上次登录是否勾了「记住我」：登录页用它初始化勾选框 */
export function readRememberPreference(): boolean {
  return localStorage.getItem(REMEMBER_KEY) === "1";
}

/** 退出登录 / 令牌失效：清掉两个介质（勾选偏好保留，下次登录仍预勾） */
export function clearAuth(): void {
  for (const store of [localStorage, sessionStorage]) {
    store.removeItem(TOKEN_KEY);
    store.removeItem(USER_KEY);
  }
}
