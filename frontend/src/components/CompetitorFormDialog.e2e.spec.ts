import { describe, it, expect, vi, beforeEach, beforeAll } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import { createPinia } from "pinia";
import ElementPlus from "element-plus";
import CompetitorFormDialog from "@/components/CompetitorFormDialog.vue";

/**
 * 端到端冒烟：不 mock api 模块，而是把底层的 axios 实例（@/api/request）换成"假 axios"，
 * 让真实的 api 层（@/api/competitor）与真实的 store（useCompetitorStore）一起跑，
 * 验证 组件 → api → store 整条链路能跑通。
 */
const requestMock = vi.hoisted(() => ({
  post: vi.fn(),
  get: vi.fn(),
  patch: vi.fn(),
  delete: vi.fn(),
}));

vi.mock("@/api/request", () => ({
  default: requestMock,
  LONG_REQUEST_TIMEOUT: 180000,
}));

const TYPES = [
  { type: "homepage", label: "官网首页", render: "browser", defaultIntervalMinutes: 1440, llmHint: "" },
  { type: "pricing", label: "定价页", render: "browser", defaultIntervalMinutes: 1440, llmHint: "" },
  { type: "changelog", label: "更新日志", render: "browser", defaultIntervalMinutes: 1440, llmHint: "" },
  { type: "blog", label: "官方博客", render: "http", defaultIntervalMinutes: 1440, llmHint: "" },
  { type: "docs", label: "帮助文档", render: "browser", defaultIntervalMinutes: 10080, llmHint: "" },
  { type: "status", label: "服务状态页", render: "http", defaultIntervalMinutes: 60, llmHint: "" },
  { type: "rss", label: "RSS 订阅", render: "http", defaultIntervalMinutes: 60, llmHint: "" },
  { type: "app_store", label: "应用商店页", render: "browser", defaultIntervalMinutes: 1440, llmHint: "" },
];

beforeAll(() => {
  (globalThis as any).ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
});

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();

  requestMock.post.mockImplementation(async (url: string, data: any) => {
    if (url === "/api/competitors/check-url") {
      return { url: data.url, ok: true, httpStatus: 200, message: "ok" };
    }
    if (url === "/api/competitors/suggest") {
      return { officialUrl: null, category: null, source: "none", message: "" };
    }
    if (url === "/api/competitors/discover-sources") {
      return { officialUrl: data.officialUrl, homepageReachable: true, sources: [] };
    }
    if (url === "/api/competitors") {
      return { id: 1, name: data.name, domain: data.officialUrl };
    }
    return {};
  });
  requestMock.get.mockImplementation(async (url: string) => {
    if (url === "/api/source-types") return [...TYPES];
    if (url === "/api/competitors") return [];
    return [];
  });
});

function mountDialog() {
  const pinia = createPinia();
  return mount(CompetitorFormDialog, {
    props: { modelValue: false },
    global: { plugins: [pinia, ElementPlus] },
  }) as any;
}

describe("添加竞品 - 端到端冒烟（组件 → api → store）", () => {
  it("填名称 → 规则预填 → 立即创建：全链路跑通并提交正确载荷", async () => {
    const wrapper = mountDialog();
    await flushPromises();
    await wrapper.setProps({ modelValue: true });
    await flushPromises();

    // 1) 名称失焦 → 本地规则预填官网（不发 AI）
    wrapper.vm.form.name = "deepseek";
    wrapper.vm.onNameBlur();
    await flushPromises();
    expect(wrapper.vm.form.officialUrl).toBe("https://deepseek.com");
    expect(wrapper.vm.urls.homepage).toBe("https://deepseek.com");

    // 2) 立即创建 → 校验官网可达(真实 api) → 新增(真实 api) → 刷新列表(真实 store)
    await wrapper.vm.handleSubmit();
    await flushPromises();

    // 校验接口确实被调用（证明真实 api + 假 axios 打通）
    const checkCall = requestMock.post.mock.calls.find(
      (c) => c[0] === "/api/competitors/check-url",
    );
    expect(checkCall).toBeTruthy();

    // 新增载荷正确
    const createCall = requestMock.post.mock.calls.find((c) => c[0] === "/api/competitors");
    expect(createCall).toBeTruthy();
    const payload = createCall![1];
    expect(payload.name).toBe("deepseek");
    expect(payload.officialUrl).toBe("https://deepseek.com");
    expect((payload.sources ?? []).map((s: any) => s.sourceType)).toContain("homepage");

    // store 保存后重新拉取列表
    expect(requestMock.get).toHaveBeenCalledWith("/api/competitors");
    wrapper.unmount();
  });

  it("官网不可达时：默认被拦截，不发新增请求", async () => {
    requestMock.post.mockImplementation(async (url: string, data: any) => {
      if (url === "/api/competitors/check-url") {
        return { url: data.url, ok: false, httpStatus: 404, message: "404" };
      }
      if (url === "/api/competitors") return { id: 1, name: data.name };
      return { officialUrl: null, category: null, source: "none", message: "" };
    });
    const wrapper = mountDialog();
    await flushPromises();
    await wrapper.setProps({ modelValue: true });
    await flushPromises();

    wrapper.vm.form.name = "豆包";
    wrapper.vm.form.officialUrl = "https://doubao.com";
    await wrapper.vm.handleSubmit();
    await flushPromises();

    const createCall = requestMock.post.mock.calls.find((c) => c[0] === "/api/competitors");
    expect(createCall).toBeFalsy(); // 硬拦，未创建
    wrapper.unmount();
  });
});
