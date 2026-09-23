import { describe, it, expect, vi, beforeEach, beforeAll } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import ElementPlus from "element-plus";
import { createPinia, setActivePinia } from "pinia";
import CompetitorFormDialog from "@/components/CompetitorFormDialog.vue";
import { usePreferencesStore } from "@/stores/preferences";
import { fetchMyPreferences, saveMyPreferences } from "@/api/user";
import {
  checkSourceUrl,
  discoverSources,
  fetchSourceTypes,
  suggestCompetitor,
} from "@/api/competitor";

// ---- 类型目录 mock（与组件内 FALLBACK_TYPES 口径一致）----
const TYPES = [
  { type: "homepage", label: "官网首页", render: "browser", defaultIntervalMinutes: 1440, llmHint: "" },
  { type: "pricing", label: "定价页", render: "browser", defaultIntervalMinutes: 1440, llmHint: "" },
  { type: "changelog", label: "更新日志", render: "browser", defaultIntervalMinutes: 1440, llmHint: "" },
  { type: "blog", label: "官方博客", render: "http", defaultIntervalMinutes: 1440, llmHint: "" },
  { type: "docs", label: "帮助文档", render: "browser", defaultIntervalMinutes: 10080, llmHint: "" },
  { type: "status", label: "服务状态页", render: "http", defaultIntervalMinutes: 60, llmHint: "" },
  { type: "rss", label: "RSS 订阅", render: "http", defaultIntervalMinutes: 60, llmHint: "" },
  { type: "app_store", label: "应用商店页", render: "browser", defaultIntervalMinutes: 1440, llmHint: "" },
] as const;

const OFFICIAL_KEY = "__official__";

// 默认让校验接口“可达”，个别用例再改
function mockCheck(url: string, ok = true, message = "ok") {
  vi.mocked(checkSourceUrl).mockImplementation(async (u: string) => ({
    url: u,
    ok: u === url ? ok : ok,
    httpStatus: ok ? 200 : 404,
    message,
  }));
}

beforeAll(() => {
  // jsdom 缺 ResizeObserver，Element Plus 部分组件会用到
  (globalThis as any).ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
});

vi.mock("@/api/competitor", () => ({
  checkSourceUrl: vi.fn(),
  discoverSources: vi.fn(),
  fetchSourceTypes: vi.fn(),
  suggestCompetitor: vi.fn(),
}));

// 偏好 store 会去打这两个接口，必须挡住，否则单测里发真实请求
vi.mock("@/api/user", () => ({
  fetchMyPreferences: vi.fn(),
  saveMyPreferences: vi.fn(),
}));

const { storeMock } = vi.hoisted(() => ({
  storeMock: {
    addCompetitor: vi.fn(),
    editCompetitor: vi.fn(),
    competitors: [] as any[],
  },
}));

vi.mock("@/stores/competitor", () => ({
  useCompetitorStore: () => storeMock,
}));

let wrapper: any;

beforeEach(async () => {
  vi.clearAllMocks();
  // 组件用了 preferences store（Pinia），每个用例给一套干净的 pinia / store 实例
  setActivePinia(createPinia());
  vi.mocked(fetchMyPreferences).mockResolvedValue({
    allowUnreachableOfficial: false,
    defaultSourceTypes: ["homepage"],
    emailNotifyEnabled: true,
  });
  vi.mocked(saveMyPreferences).mockImplementation(async (patch: any) => ({
    allowUnreachableOfficial: patch.allowUnreachableOfficial ?? false,
    defaultSourceTypes: patch.defaultSourceTypes ?? ["homepage"],
    emailNotifyEnabled: patch.emailNotifyEnabled ?? true,
  }));
  vi.mocked(fetchSourceTypes).mockResolvedValue([...TYPES]);
  mockCheck(""); // 默认可达
  vi.mocked(discoverSources).mockResolvedValue({
    officialUrl: "https://example.com",
    homepageReachable: true,
    sources: [],
  });
  vi.mocked(suggestCompetitor).mockResolvedValue({
    officialUrl: null,
    category: null,
    source: "none",
    message: "",
  });
  storeMock.addCompetitor.mockReset().mockResolvedValue({});
  storeMock.editCompetitor.mockReset().mockResolvedValue({});
  storeMock.competitors = [];

  wrapper = mount(CompetitorFormDialog, {
    props: { modelValue: false },
    global: { plugins: [ElementPlus] },
  });
  await flushPromises();
  // 触发 visible false→true，让 watch(visible) 执行 initialize()（loadTypeOptions + applyDefaults 默认勾选三页）
  await wrapper.setProps({ modelValue: true });
  await flushPromises();
  // 重置模块级去重标记，保证用例独立
  if ("lastSuggestedName" in wrapper.vm) wrapper.vm.lastSuggestedName = "";
});

const vm = () => wrapper.vm;

/** 勾选某个监控页（TYPES 里的类型） */
function selectType(type: string) {
  const opt = TYPES.find((t) => t.type === type)!;
  if (!vm().selected.includes(type)) vm().toggleType(opt as any);
}

describe("添加竞品 - 名称失焦自动预填（本地规则，不发请求）", () => {
  it("英文名 → 按规则预填官网+页面，状态为未检测", () => {
    selectType("pricing");
    selectType("changelog");
    vm().form.name = "deepseek";
    vm().onNameBlur();
    expect(vm().form.officialUrl).toBe("https://deepseek.com");
    expect(vm().urls.homepage).toBe("https://deepseek.com");
    expect(vm().urls.pricing).toBe("https://deepseek.com/pricing");
    expect(vm().urls.changelog).toBe("https://deepseek.com/changelog");
    expect(vm().checkState[OFFICIAL_KEY]).toBe(""); // 未检测
    expect(vm().checkState.homepage).toBe("");
  });

  it("中文名 → 不生成无效网址，字段留空", () => {
    vm().form.name = "豆包";
    vm().onNameBlur();
    expect(vm().form.officialUrl).toBe("");
    expect(vm().urls.homepage).toBe("");
  });

  it("同名再次失焦 → 不重复覆盖（也保留用户手动改动）", () => {
    vm().form.name = "deepseek";
    vm().onNameBlur();
    const first = vm().form.officialUrl;
    // 用户手动改了官网
    vm().form.officialUrl = "https://manual.com";
    vm().onNameBlur(); // 再次同名失焦
    expect(vm().form.officialUrl).toBe("https://manual.com"); // 未被规则覆盖
    expect(first).toBe("https://deepseek.com");
  });
});

describe("添加竞品 - 手动填官网失焦", () => {
  it("反推名称 + 按规则预填页面 + 只检测官网本身", async () => {
    vi.mocked(checkSourceUrl).mockResolvedValue({ url: "", ok: true, httpStatus: 200, message: "ok" });
    selectType("pricing");
    vm().form.officialUrl = "https://doubao.com";
    vm().onUrlBlur();
    expect(vm().form.name).toBe("Doubao"); // 从域名反推
    expect(vm().urls.homepage).toBe("https://doubao.com");
    expect(vm().urls.pricing).toBe("https://doubao.com/pricing");
    await flushPromises();
    expect(vm().checkState[OFFICIAL_KEY]).toBe("ok"); // 官网被检测
    // 页面只预填未检测（不自动检测页面）
    expect(vm().checkState.pricing).toBe("");
  });

  it("已通过官网被手改后再次失焦 → 重新检测新值（不被 ok 跳过）", async () => {
    vi.mocked(checkSourceUrl).mockResolvedValue({ url: "", ok: true, httpStatus: 200, message: "ok" });
    vm().form.officialUrl = "https://a.com";
    vm().onUrlBlur();
    await flushPromises();
    expect(vm().checkState[OFFICIAL_KEY]).toBe("ok");
    const calls1 = vi.mocked(checkSourceUrl).mock.calls.length;

    // 模拟手动改官网：先清状态（@input 行为），再失焦
    vm().form.officialUrl = "https://b.com";
    vm().clearCheck(OFFICIAL_KEY);
    vm().onUrlBlur();
    await flushPromises();
    expect(vm().form.officialUrl).toBe("https://b.com");
    expect(vm().checkState[OFFICIAL_KEY]).toBe("ok");
    expect(vi.mocked(checkSourceUrl).mock.calls.length).toBeGreaterThan(calls1); // 确实重新检测了
  });
});

describe("添加竞品 - 页面网址失焦只检测单个", () => {
  it("未检测页面失焦 → 检测该页", async () => {
    vi.mocked(checkSourceUrl).mockResolvedValue({ url: "", ok: true, httpStatus: 200, message: "ok" });
    selectType("pricing");
    vm().form.officialUrl = "https://doubao.com";
    vm().onUrlBlur();
    await flushPromises();
    vm().urls.pricing = "https://doubao.com/pricing";
    vm().checkOne("pricing", vm().urls.pricing);
    await flushPromises();
    expect(vm().checkState.pricing).toBe("ok");
  });

  it("已通过页面失焦 → 跳过不重复检测", async () => {
    vi.mocked(checkSourceUrl).mockResolvedValue({ url: "", ok: true, httpStatus: 200, message: "ok" });
    selectType("pricing");
    vm().form.officialUrl = "https://doubao.com";
    vm().onUrlBlur();
    await flushPromises();
    vm().urls.pricing = "https://doubao.com/pricing";
    await vm().checkOne("pricing", vm().urls.pricing);
    await flushPromises();
    const calls = vi.mocked(checkSourceUrl).mock.calls.length;
    // 已是 ok，再次失焦不应再发请求
    await vm().checkOne("pricing", vm().urls.pricing);
    expect(vi.mocked(checkSourceUrl).mock.calls.length).toBe(calls);
    expect(vm().checkState.pricing).toBe("ok");
  });

  it("手动编辑页面 → 标记手动，官网变动不再被覆盖", async () => {
    vi.mocked(checkSourceUrl).mockResolvedValue({ url: "", ok: true, httpStatus: 200, message: "ok" });
    selectType("pricing");
    vm().form.officialUrl = "https://doubao.com";
    vm().onUrlBlur();
    await flushPromises();
    // 用户手动改了定价页
    vm().urls.pricing = "https://doubao.com/custom-price";
    vm().onPageUrlInput("pricing");
    expect(vm().manualUrlEdited.pricing).toBe(true);
    // 改官网再失焦，手动页面应保持不变
    vm().form.officialUrl = "https://new.com";
    vm().onUrlBlur();
    await flushPromises();
    expect(vm().urls.pricing).toBe("https://doubao.com/custom-price");
  });
});

describe("添加竞品 - 勾选 / 取消勾选页面", () => {
  it("官网已填 → 勾选新页面按本地规则自动补", () => {
    vm().form.officialUrl = "https://doubao.com";
    const blogOpt = TYPES.find((t) => t.type === "blog")!;
    vm().toggleType(blogOpt);
    expect(vm().urls.blog).toBe("https://doubao.com/blog");
  });

  it("官网没填 → 勾选新页面保持空白", () => {
    vm().form.officialUrl = "";
    const statusOpt = TYPES.find((t) => t.type === "status")!;
    vm().toggleType(statusOpt);
    expect(vm().urls.status).toBe("");
  });

  it("取消勾选再重新勾选 → 保留通过状态与网址", async () => {
    vi.mocked(checkSourceUrl).mockResolvedValue({ url: "", ok: true, httpStatus: 200, message: "ok" });
    vm().form.officialUrl = "https://doubao.com";
    const blogOpt = TYPES.find((t) => t.type === "blog")!;
    vm().toggleType(blogOpt);
    vm().urls.blog = "https://doubao.com/blog";
    vm().checkState.blog = "ok"; // 模拟已检测通过
    // 取消
    vm().toggleType(blogOpt);
    expect(vm().selected.includes("blog")).toBe(false);
    // 重新勾选
    vm().toggleType(blogOpt);
    expect(vm().urls.blog).toBe("https://doubao.com/blog");
    expect(vm().checkState.blog).toBe("ok"); // 通过状态保留
  });

  it("取消勾选期间官网变动 → 非手动页面重新猜测并清掉旧通过", async () => {
    vi.mocked(checkSourceUrl).mockResolvedValue({ url: "", ok: true, httpStatus: 200, message: "ok" });
    vm().form.officialUrl = "https://doubao.com";
    const blogOpt = TYPES.find((t) => t.type === "blog")!;
    vm().toggleType(blogOpt);
    vm().urls.blog = "https://doubao.com/blog";
    vm().checkState.blog = "ok";
    vm().toggleType(blogOpt); // 取消
    vm().form.officialUrl = "https://new.com"; // 期间改官网
    vm().toggleType(blogOpt); // 重新勾选
    expect(vm().urls.blog).toBe("https://new.com/blog"); // 跟随新官网
    expect(vm().checkState.blog).toBe(""); // 旧通过作废
  });

  it("点删除按钮（preserve=false）→ 不保留已填网址（即使已通过），重新勾选回到默认状态", async () => {
    vi.mocked(checkSourceUrl).mockResolvedValue({ url: "", ok: true, httpStatus: 200, message: "ok" });
    vm().form.officialUrl = "https://doubao.com";
    const blogOpt = TYPES.find((t) => t.type === "blog")!;
    vm().toggleType(blogOpt);
    // 用户手填一个非默认猜测的网址并标记为已通过
    vm().urls.blog = "https://doubao.com/my-custom-feed";
    vm().onPageUrlInput("blog");
    vm().checkState.blog = "ok";
    // 点删除按钮（与行内 danger 删除按钮等价：preserve=false）
    vm().removeType("blog", false);
    expect(vm().selected.includes("blog")).toBe(false);
    // 重新勾选
    vm().toggleType(blogOpt);
    // 默认按官网规则猜测，不复活删除前手填的网址与通过状态
    expect(vm().urls.blog).toBe("https://doubao.com/blog"); // 默认猜测
    expect(vm().urls.blog).not.toBe("https://doubao.com/my-custom-feed"); // 手填的不恢复
    expect(vm().checkState.blog).toBeFalsy(); // 通过状态不复活（默认未检测）
    expect(vm().manualUrlEdited.blog).toBeFalsy(); // 不标记为手动
  });
});

describe("添加竞品 - 检测网址按钮（跳过已通过）", () => {
  it("已勾选页面网址空白 → 提示待填并中止（不发任何请求）", async () => {
    // 官网为空 → 三个默认已勾选页面都没有网址
    expect(vm().selected.length).toBeGreaterThan(0);
    await vm().runManualCheck();
    await flushPromises();
    expect(vi.mocked(checkSourceUrl)).not.toHaveBeenCalled();
  });

  it("已通过的页面不被重复检测；未通过的会被检测", async () => {
    vi.mocked(checkSourceUrl).mockImplementation(async (u: string) => ({
      url: u,
      ok: u !== "https://doubao.com/bad", // 这个故意不通
      httpStatus: u !== "https://doubao.com/bad" ? 200 : 404,
      message: u !== "https://doubao.com/bad" ? "ok" : "404",
    }));
    selectType("pricing");
    selectType("changelog");
    vm().form.officialUrl = "https://doubao.com";
    vm().onUrlBlur();
    await flushPromises();
    vm().urls.pricing = "https://doubao.com/pricing";
    await vm().checkOne("pricing", vm().urls.pricing); // 通过
    await flushPromises();
    // 手动把更新日志改成不通的地址并标记手动（避免被官网同步覆盖），再检测
    vm().urls.changelog = "https://doubao.com/bad";
    vm().onPageUrlInput("changelog");
    await vm().checkOne("changelog", vm().urls.changelog);
    await flushPromises();
    expect(vm().checkState.pricing).toBe("ok");
    expect(vm().checkState.changelog).toBe("fail");

    vi.mocked(checkSourceUrl).mockClear();
    await vm().runManualCheck();
    await flushPromises();
    const after = vi.mocked(checkSourceUrl).mock.calls.map((c) => c[0]);
    expect(after).toContain("https://doubao.com/bad"); // 未通过被检测
    expect(after).not.toContain("https://doubao.com/pricing"); // 已通过跳过
  });
});

describe("添加竞品 - 智能检测填充（先检测，未通过/空白才 AI 找）", () => {
  it("已通过页面不被 AI 修改，且被放进 discover 的 skipTypes", async () => {
    // 让“更新日志”这一页检测不通，从而触发 discover；homepage/pricing 保持通过
    vi.mocked(checkSourceUrl).mockImplementation(async (u: string) => ({
      url: u,
      ok: u !== "https://doubao.com/changelog",
      httpStatus: u !== "https://doubao.com/changelog" ? 200 : 404,
      message: u !== "https://doubao.com/changelog" ? "ok" : "404",
    }));
    vi.mocked(discoverSources).mockResolvedValue({
      officialUrl: "https://doubao.com",
      homepageReachable: true,
      sources: [
        { sourceType: "changelog", label: "更新日志", url: "https://doubao.com/changelog-real", found: true, origin: "link", httpStatus: 200 },
      ],
    });
    selectType("pricing");
    selectType("changelog");
    vm().form.officialUrl = "https://doubao.com";
    vm().onUrlBlur();
    await flushPromises();
    // homepage/pricing 通，changelog 不通
    await vm().checkOne(OFFICIAL_KEY, "https://doubao.com");
    await vm().checkOne("homepage", "https://doubao.com");
    await vm().checkOne("pricing", "https://doubao.com/pricing");
    await vm().checkOne("changelog", "https://doubao.com/changelog");
    await flushPromises();
    expect(vm().checkState.homepage).toBe("ok");
    expect(vm().checkState.changelog).toBe("fail");

    await vm().autoDetectFill(true, true);
    await flushPromises();
    // 已通过的页面保持原样，未被 AI 改动
    expect(vm().checkState.homepage).toBe("ok");
    expect(vm().urls.homepage).toBe("https://doubao.com");
    // discoverSources 应把已通过类型放入 skipTypes
    const skip = vi.mocked(discoverSources).mock.calls[0][1] as string[];
    expect(skip).toContain("homepage");
    expect(skip).toContain("pricing");
    // 不通的更新日志被 AI 找到并回填为通过
    expect(vm().urls.changelog).toBe("https://doubao.com/changelog-real");
    expect(vm().checkState.changelog).toBe("ok");
  });

  it("检测不通（即“空白未填/猜错”）的页面才会被 AI 寻找并回填为通过", async () => {
    // 博客猜测地址不通 → 触发寻找
    vi.mocked(checkSourceUrl).mockImplementation(async (u: string) => ({
      url: u,
      ok: u !== "https://doubao.com/blog",
      httpStatus: u !== "https://doubao.com/blog" ? 200 : 404,
      message: u !== "https://doubao.com/blog" ? "ok" : "404",
    }));
    const blogOpt = TYPES.find((t) => t.type === "blog")!;
    vm().toggleType(blogOpt); // 勾选博客
    vm().form.officialUrl = "https://doubao.com";
    vm().onUrlBlur(); // 同步出博客猜测地址
    await flushPromises();
    await vm().checkOne("blog", "https://doubao.com/blog"); // 检测不通
    await flushPromises();
    expect(vm().checkState.blog).toBe("fail");

    vi.mocked(discoverSources).mockResolvedValue({
      officialUrl: "https://doubao.com",
      homepageReachable: true,
      sources: [
        { sourceType: "blog", label: "官方博客", url: "https://doubao.com/blog-real", found: true, origin: "link", httpStatus: 200 },
      ],
    });
    await vm().autoDetectFill(true, true);
    await flushPromises();
    expect(vm().urls.blog).toBe("https://doubao.com/blog-real");
    expect(vm().checkState.blog).toBe("ok"); // AI 找回归位即通过
  });
});

describe("添加竞品 - 立即创建/保存修改（硬拦截：存在未通过就不让保存）", () => {
  it("存在未通过网址 → 提示且不保存", async () => {
    vi.mocked(checkSourceUrl).mockResolvedValue({ url: "", ok: false, httpStatus: 404, message: "404" });
    vm().form.name = "豆包";
    vm().form.officialUrl = "https://doubao.com";
    await vm().handleSubmit();
    await flushPromises();
    expect(storeMock.addCompetitor).not.toHaveBeenCalled();
  });

  it("全部通过 → 直接保存", async () => {
    vi.mocked(checkSourceUrl).mockResolvedValue({ url: "", ok: true, httpStatus: 200, message: "ok" });
    vm().form.name = "豆包";
    vm().form.officialUrl = "https://doubao.com";
    await vm().handleSubmit();
    await flushPromises();
    expect(storeMock.addCompetitor).toHaveBeenCalledTimes(1);
  });

  it("没有勾选任何页面 → 提示且不保存", async () => {
    vm().form.name = "豆包";
    vm().form.officialUrl = "https://doubao.com";
    [...vm().selected].forEach((t: string) => vm().removeType(t));
    expect(vm().selected.length).toBe(0);
    await vm().handleSubmit();
    await flushPromises();
    expect(storeMock.addCompetitor).not.toHaveBeenCalled();
  });

  it("手动清空的页面按空处理 → 提交时提示待填、不保存", async () => {
    vi.mocked(checkSourceUrl).mockResolvedValue({ url: "", ok: true, httpStatus: 200, message: "ok" });
    selectType("pricing");
    vm().form.name = "豆包";
    vm().form.officialUrl = "https://doubao.com";
    vm().onUrlBlur();
    await flushPromises();
    vm().urls.pricing = "";
    vm().onPageUrlInput("pricing"); // 用户手动清空定价页
    await vm().handleSubmit();
    await flushPromises();
    expect(storeMock.addCompetitor).not.toHaveBeenCalled();
  });
});

describe("添加竞品 - 边界修复", () => {
  it("编辑模式：官网失焦不覆盖已保存的页面网址", async () => {
    vi.mocked(checkSourceUrl).mockResolvedValue({ url: "", ok: true, httpStatus: 200, message: "ok" });
    const w2: any = mount(CompetitorFormDialog, {
      props: {
        modelValue: false,
        competitor: {
          id: 1,
          name: "X",
          domain: "https://x.com",
          category: "AI",
          sources: [
            {
              id: 1,
              competitorId: 1,
              sourceType: "pricing",
              label: "定价页",
              name: "",
              url: "https://x.com/plans",
              renderMode: "browser",
              intervalMinutes: 1440,
            },
          ],
        } as any,
      },
      global: { plugins: [ElementPlus] },
    });
    await flushPromises();
    await w2.setProps({ modelValue: true });
    await flushPromises();
    expect(w2.vm.urls.pricing).toBe("https://x.com/plans");
    w2.vm.onUrlBlur(); // 碰一下官网再离开
    await flushPromises();
    expect(w2.vm.urls.pricing).toBe("https://x.com/plans"); // 未被规则猜测覆盖
    w2.unmount();
  });

  it("检测中修改字段 → 旧请求结果被丢弃，不覆盖新值状态", async () => {
    let resolveFn: (v: unknown) => void = () => {};
    vi.mocked(checkSourceUrl).mockImplementationOnce(
      () => new Promise((res) => (resolveFn = res)) as any,
    );
    vm().urls.pricing = "https://doubao.com/old";
    const p = vm().checkOne("pricing", "https://doubao.com/old");
    // 请求还没回来，用户就改成了新值
    vm().urls.pricing = "https://doubao.com/new";
    vm().onPageUrlInput("pricing"); // 清状态并作废在途请求
    resolveFn({ url: "https://doubao.com/old", ok: true, httpStatus: 200, message: "ok" });
    await p;
    await flushPromises();
    expect(vm().checkState.pricing).toBe(""); // 旧结果没落到新值上
  });

  it("同一网址（官网地址与官网首页同址）状态同步一致", async () => {
    vi.mocked(checkSourceUrl).mockResolvedValue({ url: "", ok: true, httpStatus: 200, message: "ok" });
    vm().form.officialUrl = "https://doubao.com";
    vm().onUrlBlur();
    await flushPromises();
    expect(vm().checkState[OFFICIAL_KEY]).toBe("ok");
    expect(vm().checkState.homepage).toBe("ok"); // 同址一并点亮
  });

  it("AI 找回的页面地址，改官网后不被猜测覆盖", async () => {
    vi.mocked(checkSourceUrl).mockImplementation(async (u: string) => ({
      url: u,
      ok: u !== "https://doubao.com/blog",
      httpStatus: u !== "https://doubao.com/blog" ? 200 : 404,
      message: u !== "https://doubao.com/blog" ? "ok" : "404",
    }));
    const blogOpt = TYPES.find((t) => t.type === "blog")!;
    vm().toggleType(blogOpt);
    vm().form.officialUrl = "https://doubao.com";
    vm().onUrlBlur();
    await flushPromises();
    await vm().checkOne("blog", "https://doubao.com/blog");
    await flushPromises();
    vi.mocked(discoverSources).mockResolvedValue({
      officialUrl: "https://doubao.com",
      homepageReachable: true,
      sources: [
        { sourceType: "blog", label: "官方博客", url: "https://doubao.com/blog-real", found: true, origin: "link", httpStatus: 200 },
      ],
    });
    await vm().autoDetectFill(true, true);
    await flushPromises();
    expect(vm().urls.blog).toBe("https://doubao.com/blog-real");
    // 改官网 → 已确认的 blog 地址保留
    vm().form.officialUrl = "https://new.com";
    vm().onUrlBlur();
    await flushPromises();
    expect(vm().urls.blog).toBe("https://doubao.com/blog-real");
  });

  it("已填官网不可达 → 智能检测填充改用 AI 推断的官网", async () => {
    vi.mocked(suggestCompetitor).mockResolvedValue({
      officialUrl: "https://doubao.com",
      category: null,
      source: "llm",
      message: "",
    });
    vi.mocked(checkSourceUrl).mockImplementation(async (u: string) => ({
      url: u,
      ok: u === "https://doubao.com",
      httpStatus: u === "https://doubao.com" ? 200 : 404,
      message: u === "https://doubao.com" ? "ok" : "404",
    }));
    vi.mocked(discoverSources).mockResolvedValue({
      officialUrl: "https://doubao.com",
      homepageReachable: true,
      sources: [],
    });
    vm().form.name = "豆包";
    vm().form.officialUrl = "https://wrong.com"; // 不可达
    await vm().autoDetectFill(true, true);
    await flushPromises();
    expect(vm().form.officialUrl).toBe("https://doubao.com");
  });
});

describe("添加竞品 - 第二轮修复", () => {
  it("检测请求失败（未能校验）不硬拦截，仍可保存", async () => {
    vi.mocked(checkSourceUrl).mockRejectedValue(new Error("network down"));
    vm().form.name = "豆包";
    vm().form.officialUrl = "https://doubao.com";
    await vm().handleSubmit();
    await flushPromises();
    expect(storeMock.addCompetitor).toHaveBeenCalledTimes(1); // 放行
  });

  it("官网未改动时再次失焦 → 不重复检测", async () => {
    vi.mocked(checkSourceUrl).mockResolvedValue({ url: "", ok: true, httpStatus: 200, message: "ok" });
    vm().form.officialUrl = "https://doubao.com";
    vm().onUrlBlur();
    await flushPromises();
    const calls = vi.mocked(checkSourceUrl).mock.calls.length;
    vm().onUrlBlur(); // 未改动，再次失焦
    await flushPromises();
    expect(vi.mocked(checkSourceUrl).mock.calls.length).toBe(calls);
  });

  it("重复竞品（同官网）→ 提示且不保存", async () => {
    vi.mocked(checkSourceUrl).mockResolvedValue({ url: "", ok: true, httpStatus: 200, message: "ok" });
    storeMock.competitors = [{ id: 9, name: "别家", domain: "https://doubao.com" }];
    vm().form.name = "豆包";
    vm().form.officialUrl = "https://doubao.com";
    await vm().handleSubmit();
    await flushPromises();
    expect(storeMock.addCompetitor).not.toHaveBeenCalled();
  });

  it("重复竞品（域名写法不同也算）→ 归一化后提示且不保存", async () => {
    vi.mocked(checkSourceUrl).mockResolvedValue({ url: "", ok: true, httpStatus: 200, message: "ok" });
    storeMock.competitors = [{ id: 9, name: "别家", domain: "doubao.com" }]; // 无协议
    vm().form.name = "豆包";
    vm().form.officialUrl = "https://doubao.com/"; // 带协议与尾斜杠
    await vm().handleSubmit();
    await flushPromises();
    expect(storeMock.addCompetitor).not.toHaveBeenCalled();
  });

  it("保存接口报错 → 不抛出、有兜底", async () => {
    vi.mocked(checkSourceUrl).mockResolvedValue({ url: "", ok: true, httpStatus: 200, message: "ok" });
    storeMock.addCompetitor.mockRejectedValue(new Error("500"));
    vm().form.name = "豆包";
    vm().form.officialUrl = "https://doubao.com";
    await expect(vm().handleSubmit()).resolves.toBeUndefined();
    await flushPromises();
  });

  it("官网带路径 → 页面猜测只用主机，避免重复拼接路径", async () => {
    vi.mocked(checkSourceUrl).mockResolvedValue({ url: "", ok: true, httpStatus: 200, message: "ok" });
    selectType("pricing");
    vm().form.officialUrl = "https://x.com/sub";
    vm().onUrlBlur();
    await flushPromises();
    expect(vm().urls.pricing).toBe("https://x.com/pricing");
  });

  it("大写协议 HTTPS:// 也能被正确识别", async () => {
    vi.mocked(checkSourceUrl).mockResolvedValue({ url: "", ok: true, httpStatus: 200, message: "ok" });
    vm().form.officialUrl = "HTTPS://x.com";
    vm().onUrlBlur();
    await flushPromises();
    expect(vm().urls.homepage).toBe("HTTPS://x.com"); // 不会拼成 https://HTTPS://...
  });
});

describe("添加竞品 - 第三轮：更丝滑的默认行为", () => {
  it("默认只勾选「官网首页」", () => {
    expect(vm().selected).toEqual(["homepage"]);
  });

  it("官网不可达 → 硬拦截、不保存", async () => {
    vi.mocked(checkSourceUrl).mockImplementation(async (u: string) => ({
      url: u,
      ok: false,
      httpStatus: 404,
      message: "404",
    }));
    vm().form.name = "豆包";
    vm().form.officialUrl = "https://doubao.com";
    await vm().handleSubmit();
    await flushPromises();
    expect(storeMock.addCompetitor).not.toHaveBeenCalled();
  });

  it("可选页不可达 → 不阻断保存，且该页被跳过（不写入创建）", async () => {
    vi.mocked(checkSourceUrl).mockImplementation(async (u: string) => ({
      url: u,
      ok: u !== "https://doubao.com/changelog",
      httpStatus: u !== "https://doubao.com/changelog" ? 200 : 404,
      message: u !== "https://doubao.com/changelog" ? "ok" : "404",
    }));
    selectType("changelog");
    vm().form.name = "豆包";
    vm().form.officialUrl = "https://doubao.com";
    await vm().handleSubmit();
    await flushPromises();
    expect(storeMock.addCompetitor).toHaveBeenCalledTimes(1);
    const payload = storeMock.addCompetitor.mock.calls[0][0];
    const types = (payload.sources ?? []).map((s: any) => s.sourceType);
    expect(types).toContain("homepage");
    expect(types).not.toContain("changelog"); // 不可达的可选页被跳过
  });

  it("猜测的页面地址显示「待验证」标记", async () => {
    vi.mocked(checkSourceUrl).mockResolvedValue({ url: "", ok: true, httpStatus: 200, message: "ok" });
    vm().form.officialUrl = "https://doubao.com";
    vm().onUrlBlur();
    await flushPromises();
    selectType("blog"); // 官网已填 → 规则猜测 /blog，未检测
    await flushPromises();
    expect(vm().checkState.blog).toBeFalsy();
    expect(vm().urls.blog).toBe("https://doubao.com/blog");
    expect(wrapper.html()).toContain("待验证");
  });

  it("AI 没找到的页面 → 保持未通过，新建时被跳过", async () => {
    vi.mocked(checkSourceUrl).mockImplementation(async (u: string) => ({
      url: u,
      ok: u !== "https://doubao.com/blog",
      httpStatus: u !== "https://doubao.com/blog" ? 200 : 404,
      message: u !== "https://doubao.com/blog" ? "ok" : "404",
    }));
    vi.mocked(discoverSources).mockResolvedValue({
      officialUrl: "https://doubao.com",
      homepageReachable: true,
      sources: [], // 一个都没找到
    });
    selectType("blog");
    vm().form.name = "豆包";
    vm().form.officialUrl = "https://doubao.com";
    await vm().autoDetectFill(true, true);
    await flushPromises();
    expect(vm().checkState.blog).toBe("fail"); // 没找到 → 仍未通过
    expect(vm().refindResult.blog).toBe("miss"); // 智能填充也走逐页，记录行内结果
    await vm().handleSubmit();
    await flushPromises();
    const last = storeMock.addCompetitor.mock.calls[storeMock.addCompetitor.mock.calls.length - 1];
    const types = ((last?.[0]?.sources) ?? []).map((s: any) => s.sourceType);
    expect(types).not.toContain("blog"); // 跳过未找到的页
  });
});

describe("添加竞品 - 编辑模式：不可达页可选择性移除", () => {
  function mountEdit() {
    vi.mocked(checkSourceUrl).mockImplementation(async (u: string) => ({
      url: u,
      ok: u !== "https://x.com/pricing",
      httpStatus: u !== "https://x.com/pricing" ? 200 : 404,
      message: u !== "https://x.com/pricing" ? "ok" : "404",
    }));
    return mount(CompetitorFormDialog, {
      props: {
        modelValue: false,
        competitor: {
          id: 1,
          name: "X",
          domain: "https://x.com",
          category: "AI",
          sources: [
            {
              id: 1,
              competitorId: 1,
              sourceType: "pricing",
              label: "定价页",
              name: "",
              url: "https://x.com/pricing",
              renderMode: "browser",
              intervalMinutes: 1440,
              lastError: "404 Not Found", // 上次抓取失败 → 编辑回填预置「不通过」，保存时重检并允许移除
            },
          ],
        } as any,
      },
      global: { plugins: [ElementPlus] },
    }) as any;
  }

  it("选「移除这些页」→ 该页不写入保存", async () => {
    const { ElMessageBox } = await import("element-plus");
    const spy = vi
      .spyOn(ElMessageBox, "confirm")
      .mockResolvedValue({ value: "", action: "confirm" } as any);
    const w = mountEdit();
    await flushPromises();
    await w.setProps({ modelValue: true });
    await flushPromises();
    await w.vm.handleSubmit();
    await flushPromises();
    expect(spy).toHaveBeenCalled();
    const last = storeMock.editCompetitor.mock.calls[storeMock.editCompetitor.mock.calls.length - 1];
    const types = ((last?.[1]?.sources) ?? []).map((s: any) => s.sourceType);
    expect(types).not.toContain("pricing");
    spy.mockRestore();
    w.unmount();
  });

  it("选「保留」→ 该页照旧写入保存", async () => {
    const { ElMessageBox } = await import("element-plus");
    const spy = vi.spyOn(ElMessageBox, "confirm").mockRejectedValue("cancel");
    const w = mountEdit();
    await flushPromises();
    await w.setProps({ modelValue: true });
    await flushPromises();
    await w.vm.handleSubmit();
    await flushPromises();
    const last = storeMock.editCompetitor.mock.calls[storeMock.editCompetitor.mock.calls.length - 1];
    const types = ((last?.[1]?.sources) ?? []).map((s: any) => s.sourceType);
    expect(types).toContain("pricing");
    spy.mockRestore();
    w.unmount();
  });
});

describe("添加竞品 - 单页「重新寻找」", () => {
  it("重新寻找：找到 → 回填并置为通过", async () => {
    vi.mocked(checkSourceUrl).mockImplementation(async (u: string) => ({
      url: u,
      ok: u !== "https://doubao.com/blog",
      httpStatus: u !== "https://doubao.com/blog" ? 200 : 404,
      message: u !== "https://doubao.com/blog" ? "ok" : "404",
    }));
    vi.mocked(discoverSources).mockResolvedValue({
      officialUrl: "https://doubao.com",
      homepageReachable: true,
      sources: [
        { sourceType: "blog", label: "官方博客", url: "https://doubao.com/blog-real", found: true, origin: "link", httpStatus: 200 },
      ],
    });
    selectType("blog");
    vm().form.officialUrl = "https://doubao.com";
    vm().urls.blog = "https://doubao.com/blog";
    await vm().checkOne("blog", "https://doubao.com/blog");
    await flushPromises();
    expect(vm().checkState.blog).toBe("fail");

    await vm().refindOne("blog");
    await flushPromises();
    expect(vm().urls.blog).toBe("https://doubao.com/blog-real");
    expect(vm().checkState.blog).toBe("ok");
  });

  it("重新寻找：仍没找到 → 保持未通过", async () => {
    vi.mocked(checkSourceUrl).mockImplementation(async (u: string) => ({
      url: u,
      ok: false,
      httpStatus: 404,
      message: "404",
    }));
    vi.mocked(discoverSources).mockResolvedValue({
      officialUrl: "https://doubao.com",
      homepageReachable: true,
      sources: [],
    });
    selectType("blog");
    vm().form.officialUrl = "https://doubao.com";
    await vm().checkOne("blog", "https://doubao.com/blog");
    await flushPromises();
    expect(vm().checkState.blog).toBe("fail");

    await vm().refindOne("blog");
    await flushPromises();
    expect(vm().checkState.blog).toBe("fail"); // 仍未找到
  });

  it("一键重新寻找：批量把能找到的补回，找不到的保留", async () => {
    vi.mocked(checkSourceUrl).mockImplementation(async (u: string) => ({
      url: u,
      ok: false,
      httpStatus: 404,
      message: "404",
    }));
    selectType("blog");
    selectType("docs");
    vm().form.officialUrl = "https://doubao.com";
    await vm().checkOne("blog", "https://doubao.com/blog");
    await vm().checkOne("docs", "https://doubao.com/docs");
    await flushPromises();
    expect(vm().checkState.blog).toBe("fail");
    expect(vm().checkState.docs).toBe("fail");

    vi.mocked(discoverSources).mockResolvedValue({
      officialUrl: "https://doubao.com",
      homepageReachable: true,
      sources: [
        { sourceType: "blog", label: "官方博客", url: "https://doubao.com/blog-real", found: true, origin: "link", httpStatus: 200 },
      ],
    });
    await vm().refindAll();
    await flushPromises();
    expect(vm().checkState.blog).toBe("ok");
    expect(vm().urls.blog).toBe("https://doubao.com/blog-real");
    expect(vm().checkState.docs).toBe("fail"); // 仍没找到，保留
  });
});

describe("添加竞品 - 官网不可达放行 与 批量入口", () => {
  it("官网不可达：默认硬拦（未勾选放行）", async () => {
    vi.mocked(checkSourceUrl).mockImplementation(async (u: string) => ({
      url: u,
      ok: false,
      httpStatus: 404,
      message: "404",
    }));
    vm().form.name = "豆包";
    vm().form.officialUrl = "https://doubao.com";
    await vm().handleSubmit();
    await flushPromises();
    expect(storeMock.addCompetitor).not.toHaveBeenCalled();
  });

  it("官网不可达但勾选「也先创建」→ 仍保存，且保留与官网同址的首页", async () => {
    vi.mocked(checkSourceUrl).mockImplementation(async (u: string) => ({
      url: u,
      ok: false,
      httpStatus: 404,
      message: "404",
    }));
    vm().form.name = "豆包";
    vm().form.officialUrl = "https://doubao.com";
    vm().allowUnreachableOfficial = true;
    await vm().handleSubmit();
    await flushPromises();
    expect(storeMock.addCompetitor).toHaveBeenCalledTimes(1);
    const payload = storeMock.addCompetitor.mock.calls[0][0];
    const types = (payload.sources ?? []).map((s: any) => s.sourceType);
    expect(types).toContain("homepage"); // 与官网同址，随官网一起保留
  });

  it("存在未解决页面时，footer 显示「重新寻找全部」入口", async () => {
    vi.mocked(checkSourceUrl).mockImplementation(async (u: string) => ({
      url: u,
      ok: false,
      httpStatus: 404,
      message: "404",
    }));
    selectType("blog");
    vm().form.officialUrl = "https://doubao.com";
    await vm().checkOne("blog", "https://doubao.com/blog");
    await flushPromises();
    expect(vm().hasUnresolved).toBe(true);
    expect(wrapper.html()).toContain("重新寻找全部");
  });

  it("重新寻找：逐页进行并记录 x/y 进度", async () => {
    vi.mocked(discoverSources).mockResolvedValue({
      officialUrl: "https://doubao.com",
      homepageReachable: true,
      sources: [],
    });
    vi.mocked(checkSourceUrl).mockResolvedValue({ url: "", ok: false, httpStatus: 404, message: "404" });
    selectType("blog");
    selectType("docs");
    vm().form.officialUrl = "https://doubao.com";
    await vm().checkOne("blog", "https://doubao.com/blog");
    await vm().checkOne("docs", "https://doubao.com/docs");
    await flushPromises();

    vi.mocked(discoverSources).mockClear();
    await vm().refindAll();
    await flushPromises();
    expect(vi.mocked(discoverSources)).toHaveBeenCalledTimes(2); // 逐页各一次
    expect(vm().checkProgress.total).toBe(2);
    expect(vm().checkProgress.done).toBe(2);
  });

  it("「官网放行」偏好来自服务端：新会话（新 store）打开弹窗仍生效", async () => {
    // 换一套 pinia＝模拟"下次打开"：store 会重新向服务端读偏好
    setActivePinia(createPinia());
    vi.mocked(fetchMyPreferences).mockResolvedValue({
      allowUnreachableOfficial: true,
      defaultSourceTypes: ["homepage"],
      emailNotifyEnabled: true,
    });
    const w: any = mount(CompetitorFormDialog, {
      props: { modelValue: false },
      global: { plugins: [ElementPlus] },
    });
    await flushPromises();
    await w.setProps({ modelValue: true });
    await flushPromises();
    expect(w.vm.allowUnreachableOfficial).toBe(true);
    // 回填偏好也会写回一次（值与服务端一致，重复提交无害）
    expect(vi.mocked(saveMyPreferences)).toHaveBeenCalledWith({
      allowUnreachableOfficial: true,
    });
    w.unmount();
  });

  it("设置页改了偏好：同一个 store，重开弹窗立刻用新值", async () => {
    expect(vm().allowUnreachableOfficial).toBe(false);
    // 设置页与弹窗共用同一个 preferences store（偏好跟账号走，不再走 localStorage）
    usePreferencesStore().allowUnreachableOfficial = true;
    await wrapper.setProps({ modelValue: false });
    await wrapper.setProps({ modelValue: true });
    await flushPromises();
    expect(vm().allowUnreachableOfficial).toBe(true);
  });

  it("默认勾选页面跟随服务端偏好", async () => {
    usePreferencesStore().defaultSourceTypes = ["homepage", "pricing"];
    await wrapper.setProps({ modelValue: false });
    await wrapper.setProps({ modelValue: true });
    await flushPromises();
    expect(vm().selected).toEqual(["homepage", "pricing"]);
  });

  it("重新寻找的行内结果：未找到=miss，找到=found", async () => {
    vi.mocked(checkSourceUrl).mockResolvedValue({ url: "", ok: false, httpStatus: 404, message: "404" });
    vi.mocked(discoverSources).mockResolvedValue({
      officialUrl: "https://doubao.com",
      homepageReachable: true,
      sources: [],
    });
    selectType("blog");
    vm().form.officialUrl = "https://doubao.com";
    await vm().checkOne("blog", "https://doubao.com/blog");
    await flushPromises();

    await vm().refindOne("blog"); // 没找到
    await flushPromises();
    expect(vm().refindResult.blog).toBe("miss");
    expect(wrapper.html()).toContain("未找到");

    vi.mocked(discoverSources).mockResolvedValue({
      officialUrl: "https://doubao.com",
      homepageReachable: true,
      sources: [
        { sourceType: "blog", label: "官方博客", url: "https://doubao.com/blog-real", found: true, origin: "link", httpStatus: 200 },
      ],
    });
    await vm().refindOne("blog"); // 找到
    await flushPromises();
    expect(vm().refindResult.blog).toBe("found");
    // 找到后不再显示「未找到」文字，行内显示绿色对勾（已通过状态）
    expect(wrapper.html()).not.toContain("未找到");
    expect(vm().checkState.blog).toBe("ok");
  });
});
