import { ElMessage, ElMessageBox } from "element-plus";
import { getTokenExp, readRememberPreference } from "@/utils/authStorage";
import { useAuthStore } from "@/stores/auth";

/**
 * 会话看守（企业 SaaS 式「即将过期 → 续期」体验）。
 *
 * 目标：不要让用户在毫无预兆的情况下被踢回登录页。
 * - 令牌**到期前 5 分钟**弹一次提醒：「保持登录」→ 调后端续期接口换发新令牌；
 *   「稍后再说」/ 关闭 → 不续期，计时继续，到点强制退出。
 * - 另起一个 30s 兜底巡检：防止页面被挂起 / 定时器被节流导致「到点没踢人」。
 *
 * 启动/停止：由已登录壳组件 `AppLayout.vue` 在挂载/卸载时调用，
 * 所以只在 `/app/*` 区域生效，登录页与落地页不参与。
 * 令牌真正过期后仍走请求拦截器 / SSE 断流那套统一登出，这里只是「提前提醒」这一层。
 */

/** 到期前多久开始提醒续期 */
const RENEW_WARN_MS = 5 * 60 * 1000;
/** 兜底巡检间隔（防定时器被浏览器节流/挂起而不准） */
const TICK_MS = 30 * 1000;
/**
 * 提醒定时器的单步上限。
 * setTimeout 延迟超过 2^31-1 ms（约 24.8 天）会因 32 位溢出**立即触发**
 * （MDN 明确记载的浏览器行为）：「记住我」30 天令牌的提醒延迟 ≈ 2.59×10⁹ ms
 * 正好超限 → 定时器一排定就触发 → 每次刷新都弹「即将过期」。
 * 所以长寿命令牌按「每小时一跳、到点重查剩余」逐步逼近提醒窗口。
 */
const WARN_STEP_MS = 60 * 60 * 1000;

let warnTimer: ReturnType<typeof setTimeout> | undefined;
let tickTimer: ReturnType<typeof setInterval> | undefined;
/** 本周期是否已提醒过，避免重复弹窗；续期成功后重置以便下一周期再提醒 */
let warned = false;
/** 续期请求进行中：防止连点「保持登录」重复换发 */
let renewing = false;
/**
 * 令牌寿命异常标记：续期成功后新令牌剩余仍不足提醒窗口（5 分钟），
 * 说明客户端时钟可能被快进（改过系统时间/双系统漂移）或后端 TTL 配得过短。
 * 此时继续弹窗只会陷入「刷新→弹窗→续期→刷新→弹窗」死循环，改为一一次警告 + 停弹，
 * 真正过期仍由 30s 巡检与后端 401 兜底。
 */
let ttlAbnormal = false;

function clearTimers(): void {
  if (warnTimer) {
    clearTimeout(warnTimer);
    warnTimer = undefined;
  }
  if (tickTimer) {
    clearInterval(tickTimer);
    tickTimer = undefined;
  }
}

/** 令牌剩余毫秒数；解析不出 exp 返回 null */
function msLeftOfToken(): number | null {
  const exp = getTokenExp();
  if (exp === null) return null;
  return exp * 1000 - Date.now();
}

/** 令牌已过期：停止看守并走统一登出（整页跳登录，由 store.logout 完成） */
function forceLogout(): void {
  stopSessionWatch();
  useAuthStore().logout();
}

/** 按当前令牌的 exp 排一个「到期前 5 分钟」的提醒定时器；已过期则立即强退 */
function scheduleWarn(): void {
  if (ttlAbnormal) return; // 寿命异常（见 ttlAbnormal 注释）：不再弹窗，交给兜底
  if (warnTimer) {
    clearTimeout(warnTimer);
    warnTimer = undefined;
  }
  const msLeft = msLeftOfToken();
  if (msLeft === null) return; // 解析不出 exp：交给后端 401 兜底，前端不误判
  if (msLeft <= 0) {
    forceLogout();
    return;
  }
  const delay = msLeft - RENEW_WARN_MS;
  if (delay <= 0) {
    void promptRenew();
    return;
  }
  // 长寿命令牌（如记住我 30 天）延迟会超 setTimeout 上限 → 溢出立即触发 → 刷新必弹窗。
  // 钳到每小时一跳：到点重查剩余时间，仍在窗口外就重新排定，逐步逼近。
  warnTimer = setTimeout(() => {
    const left = msLeftOfToken();
    if (left === null) return; // 解析不出 exp：交给后端 401 兜底
    if (left <= RENEW_WARN_MS) {
      void promptRenew();
    } else {
      scheduleWarn();
    }
  }, Math.min(delay, WARN_STEP_MS));
}

/** 续期：用仍有效的令牌换新的，成功后重置计时（时长沿用本地「记住我」偏好） */
async function renew(): Promise<void> {
  if (renewing) return;
  renewing = true;
  try {
    const remember = readRememberPreference();
    await useAuthStore().renewSession(remember);
    ElMessage.success("登录状态已延长");
    // 防死循环：续期后新令牌剩余仍不足提醒窗口 → 时钟被快进或 TTL 过短，
    // 置异常标记停掉自动弹窗，并明确告知用户原因（而不是无限弹「5 分钟后过期」）
    const msLeft = msLeftOfToken();
    if (msLeft !== null && msLeft < RENEW_WARN_MS) {
      ttlAbnormal = true;
      ElMessage.warning({
        message:
          "续期成功，但令牌剩余时间仍不足 5 分钟：请检查本机系统时间是否被修改过，或后端令牌有效期配置是否过短",
        duration: 8000,
      });
      return;
    }
    scheduleWarn();
  } catch (e) {
    // 续期失败必须让用户知道（之前被静默吞掉：点了「保持登录」却毫无反馈，
    // 用户会以为续期成功，刷新后弹窗照旧还以为是 bug）
    ElMessage.error("登录续期失败，请重新登录");
    throw e;
  } finally {
    renewing = false;
  }
}

/** 到期前提醒一次：点「保持登录」→ 续期；「稍后再说」/ 关闭 → 不续，到点强退 */
async function promptRenew(): Promise<void> {
  if (warned || renewing) return;
  warned = true;
  // 文案用真实剩余时间（可能已不足 5 分钟才弹），不写死「5 分钟」
  const msLeft = msLeftOfToken() ?? RENEW_WARN_MS;
  const minutes = Math.ceil(msLeft / 60000);
  const when =
    msLeft < 60_000 ? "不足 1 分钟" : `${minutes} 分钟`;
  try {
    await ElMessageBox.confirm(
      `登录状态将在 ${when}后过期，是否保持登录？`,
      "登录即将过期",
      {
        confirmButtonText: "保持登录",
        cancelButtonText: "稍后再说",
        type: "warning",
        closeOnClickModal: false,
      },
    );
    await renew();
  } catch {
    // 用户选择「稍后再说」/ 关闭，或续期失败：不续，交给到点强退；允许下一轮再提醒
    warned = false;
  }
}

/** 兜底巡检：到点仍未续期就强制退出 */
function tick(): void {
  const exp = getTokenExp();
  if (exp === null) return;
  if (Date.now() >= exp * 1000) forceLogout();
}

/** 进入已登录区域时启动（AppLayout onMounted） */
export function startSessionWatch(): void {
  stopSessionWatch();
  scheduleWarn();
  tickTimer = setInterval(tick, TICK_MS);
}

/** 离开已登录区域 / 强退时停止（AppLayout onUnmounted） */
export function stopSessionWatch(): void {
  clearTimers();
  warned = false;
  renewing = false;
}
