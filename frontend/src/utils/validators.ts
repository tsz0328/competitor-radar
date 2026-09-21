/**
 * 前端轻量校验（与后端 `app/core/validators.py` 保持同一套口径）。
 *
 * 为什么前后端各写一遍：前端这份只为「别让用户白等一次请求」。所以口径宁可按
 * **后端更宽**的那一档来，别出现「前端说格式不对、后端其实能收」这种自相矛盾的拦截。
 *
 * - 邮箱：正则与后端逐字一致——必须有且仅有一个 @，两侧非空且都不含空白，域名部分带点。
 * - 账号：3–30 位，仅 `a-z 0-9 _ -`，禁止 `@`。账号与邮箱共享同一个登录命名空间，
 *   禁止账号长得像邮箱能把「撞车」的面积从根上砍掉一大半（详见后端 validators.py）。
 */
const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;
const ACCOUNT_RE = /^[a-z0-9_-]{3,30}$/;

export const ACCOUNT_MIN_LEN = 3;
export const ACCOUNT_MAX_LEN = 30;

/** 账号名规则说明：与后端 `ACCOUNT_RULE_HINT` 同一句口径，避免两边提示不一致 */
export const ACCOUNT_RULE_HINT = "账号为 3–30 位，仅可包含字母、数字、下划线或中划线";

/** 去掉首尾空白并转小写（邮箱大小写不敏感，`A@x.com` 与 `a@x.com` 是同一个账号） */
export function normalizeEmail(raw: string): string {
  return raw.trim().toLowerCase();
}

export function isValidEmail(raw: string): boolean {
  return EMAIL_RE.test(normalizeEmail(raw));
}

/**
 * 账号名归一化：去空格 + 转小写。
 *
 * 与后端同口径——**只归一化不校验**，因为登录时对存量账号名必须宽容
 * （早期可能存过不合规的名字），格式规则只约束「新写入」的账号名。
 */
export function normalizeAccount(raw: string): string {
  return raw.trim().toLowerCase();
}

export function isValidAccount(raw: string): boolean {
  return ACCOUNT_RE.test(normalizeAccount(raw));
}

/**
 * 登录标识（账号或邮箱）的非空校验。
 *
 * 刻意**不校验格式**：两种标识的形态完全不同，用一个正则去卡只会误伤；
 * 填错了后端自然查不到，回一句「账号或密码错误」即可。
 */
export function isValidIdentifier(raw: string): boolean {
  return raw.trim().length > 0;
}
