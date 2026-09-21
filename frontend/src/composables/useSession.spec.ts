/**
 * 会话看守：30 天「记住我」令牌的提醒定时器回归。
 *
 * 背景 bug：setTimeout 延迟超过 2^31-1 ms（约 24.8 天）会因 32 位溢出**立即触发**，
 * 30 天令牌的提醒延迟 ≈ 2.59×10⁹ ms 正好超限 → 每次刷新进 /app 就弹「登录即将过期」，
 * 续期拿到的新令牌仍是 30 天 → 下次刷新接着弹。修复方式是钳到每小时一跳、逐步逼近。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

/** 当前 mock 的令牌 exp（秒级），beforeEach 里按用例改写 */
let mockedExp: number | null = null;

vi.mock("@/utils/authStorage", () => ({
  getTokenExp: vi.fn(() => mockedExp),
  readRememberPreference: vi.fn(() => true),
}));

vi.mock("element-plus", () => ({
  ElMessage: {
    success: vi.fn(),
    error: vi.fn(),
    warning: vi.fn(),
  },
  ElMessageBox: {
    confirm: vi.fn(() => Promise.resolve()),
  },
}));

const { renewSessionMock, logoutMock } = vi.hoisted(() => ({
  renewSessionMock: vi.fn(() => Promise.resolve()),
  logoutMock: vi.fn(),
}));

vi.mock("@/stores/auth", () => ({
  useAuthStore: vi.fn(() => ({
    renewSession: renewSessionMock,
    logout: logoutMock,
  })),
}));

import { ElMessageBox } from "element-plus";
import { startSessionWatch, stopSessionWatch } from "@/composables/useSession";

const DAY_MS = 86_400_000;
const WARN_MS = 5 * 60 * 1000;

beforeEach(() => {
  vi.useFakeTimers();
  vi.clearAllMocks();
});

afterEach(() => {
  stopSessionWatch();
  vi.useRealTimers();
});

describe("会话看守 - 30 天令牌提醒定时器", () => {
  it("30 天令牌：排定后立即推进几秒不得弹窗（回归：setTimeout 溢出立即触发）", async () => {
    mockedExp = Math.floor(Date.now() / 1000) + 30 * 86400;
    startSessionWatch();

    // 旧代码：延迟 2.59e9 ms 超出 setTimeout 上限 → 排定即触发 → 这里就会弹
    await vi.advanceTimersByTimeAsync(5_000);

    expect(ElMessageBox.confirm).not.toHaveBeenCalled();
  });

  it("30 天令牌：整段寿命内不弹，逼近到期前 5 分钟才弹一次", async () => {
    mockedExp = Math.floor(Date.now() / 1000) + 30 * 86400;
    startSessionWatch();

    // 快进到剩余 4 分钟：中途每个 1h 定时器到点都会重查剩余并继续排定，全程不该弹
    await vi.advanceTimersByTimeAsync(30 * DAY_MS - WARN_MS - 60_000);
    expect(ElMessageBox.confirm).not.toHaveBeenCalled();

    // 跨进 5 分钟窗口 → 下一个到点的定时器触发提醒
    await vi.advanceTimersByTimeAsync(10 * 60_000);
    expect(ElMessageBox.confirm).toHaveBeenCalledTimes(1);
    // 续期成功（renewSession mock 已 resolve），不能误报寿命异常
    expect(ElMessageBox.confirm).toHaveBeenCalledWith(
      expect.stringContaining("后过期"),
      "登录即将过期",
      expect.anything(),
    );
  });

  it("已过期的令牌：启动看守立即强制登出，不弹提醒", async () => {
    mockedExp = Math.floor(Date.now() / 1000) - 60;
    startSessionWatch();

    await vi.advanceTimersByTimeAsync(0);

    expect(ElMessageBox.confirm).not.toHaveBeenCalled();
    expect(logoutMock).toHaveBeenCalled();
  });
});
