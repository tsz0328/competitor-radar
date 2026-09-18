<script setup lang="ts">
import { computed, h, reactive, ref, watch } from "vue";
import { ElMessage, ElMessageBox, ElNotification, type FormInstance, type FormRules } from "element-plus";
import { Check, Delete, InfoFilled, Link, Loading, MagicStick, WarningFilled } from "@element-plus/icons-vue";
import { storeToRefs } from "pinia";
import { useCompetitorStore } from "@/stores/competitor";
import { usePreferencesStore } from "@/stores/preferences";
import { checkSourceUrl, discoverSources, fetchSourceTypes, suggestCompetitor } from "@/api/competitor";
import type {
  CompetitorCreatePayload,
  CompetitorItem,
  MonitorSourceInput,
  SourceType,
  SourceTypeOption,
} from "@/types/competitor";

const props = defineProps<{
  modelValue: boolean;
  /** 传入则进入编辑模式，否则为新增 */
  competitor?: CompetitorItem | null;
}>();
const emit = defineEmits<{ (e: "update:modelValue", value: boolean): void }>();

const store = useCompetitorStore();

const isEdit = computed(() => !!props.competitor);

const visible = computed({
  get: () => props.modelValue,
  set: (value) => emit("update:modelValue", value),
});

const formRef = ref<FormInstance>();
const submitting = ref(false);
const manualChecking = ref(false);
const suggesting = ref(false);
// 仅「智能检测填充」按钮(AI)点击时转圈；名称失焦的非 AI 预填不占用按钮 loading，避免误以为触发了 AI
const smartFilling = ref(false);

// 运行中（智能检测填充 / 检测网址）→ 锁定表单；「取消」通过自增令牌打断
const busy = computed(() => suggesting.value || manualChecking.value);
// 表单锁定：运行中或保存中都锁定
const locked = computed(() => busy.value || submitting.value);
let runToken = 0;
// 正在跑的批处理请求的 AbortController：取消/关闭时中止在途 HTTP
let runAbort: AbortController | null = null;
function isRunCancelled(token: number) {
  return token !== runToken;
}
function cancelRun() {
  if (!busy.value) return;
  runToken += 1;
  runAbort?.abort();
  runAbort = null;
  suggesting.value = false;
  manualChecking.value = false;
  ElMessage.info("已取消");
}

// 网址可达性校验：每个监控页（含官网）的检测状态与结论，用于行内提示
type CheckState = "" | "checking" | "ok" | "fail";
const checkState = reactive<Record<string, CheckState>>({});
const checkMsg = reactive<Record<string, string>>({});
// "未能校验"（请求失败/超时，无法判定）：不算未通过，不作为硬拦截依据
const checkUnverified = reactive<Record<string, boolean>>({});
// 批量检测进度（x/y），供底部展示，避免用户干等
const checkProgress = reactive({ done: 0, total: 0 });
// 是否存在"未解决"的页面（未通过/未能校验）→ 决定是否显示"重新寻找全部"
const hasUnresolved = computed(() =>
  selected.value.some((t) => checkState[t] === "fail" || checkUnverified[t]),
);
// 是否正在"重新寻找"
const refinding = ref(false);
// 正在被"重新寻找"的那一行（单页级状态）
const refindingType = ref<SourceType | null>(null);
// 单页"重新寻找"的行内结果提示：found=已找到 / miss=未找到
const refindResult = reactive<Record<string, "found" | "miss" | "">>({});
// 官网不可达时是否仍允许创建（用户显式勾选才放行，默认仍硬拦）；偏好存账号下，与设置页共用 store
const preferences = usePreferencesStore();
const { allowUnreachableOfficial } = storeToRefs(preferences);
watch(allowUnreachableOfficial, (v) => {
  // 初始化回填时也会触发，重复提交同一个值无害；失败提示由拦截器统一弹出
  preferences.save({ allowUnreachableOfficial: v }).catch(() => {});
});
const OFFICIAL_KEY = "__official__"; // 官网首页（可能未作为单独页面勾选）的检测键
// 记录被用户手动改过的页面网址：官网变动同步时不再被自动猜测覆盖
const manualUrlEdited = reactive<Record<string, boolean>>({});
// 取消勾选的页面暂存（含网址与检测状态），重新勾选时原样恢复、保留“通过”
const removedCache = reactive<
  Record<string, { url: string; interval: number; state: CheckState; msg: string; manual: boolean }>
>({});
// 每个字段的检测令牌：字段被编辑/清除或重新检测时自增，使在途的旧请求结果作废
const checkRun = reactive<Record<string, number>>({});

function clearCheck(key: string) {
  checkState[key] = "";
  checkMsg[key] = "";
  checkUnverified[key] = false;
  refindResult[key] = "";
  checkRun[key] = (checkRun[key] ?? 0) + 1; // 作废在途的单字段检测
}

const form = reactive({
  name: "",
  officialUrl: "",
  category: "",
  description: "",
});

// 预置分类：对齐「同类 SaaS / App 官网监控」定位，不含电商类目（可自由输入）
const categoryOptions = [
  "SaaS工具",
  "AI产品",
  "协作办公",
  "开发者工具",
  "设计工具",
  "其他",
];

const INTERVAL_CHOICES = [
  { label: "每小时", value: 60 },
  { label: "每天", value: 1440 },
  { label: "每周", value: 10080 },
];

// 注册表接口失败时的兜底，保证弹窗在任何情况下都能用
const FALLBACK_TYPES: SourceTypeOption[] = [
  { type: "homepage", label: "官网首页", render: "browser", defaultIntervalMinutes: 1440, llmHint: "" },
  { type: "pricing", label: "定价页", render: "browser", defaultIntervalMinutes: 1440, llmHint: "" },
  { type: "changelog", label: "更新日志", render: "browser", defaultIntervalMinutes: 1440, llmHint: "" },
  { type: "blog", label: "官方博客", render: "http", defaultIntervalMinutes: 1440, llmHint: "" },
  { type: "docs", label: "帮助文档", render: "browser", defaultIntervalMinutes: 10080, llmHint: "" },
  { type: "status", label: "服务状态页", render: "http", defaultIntervalMinutes: 60, llmHint: "" },
  { type: "rss", label: "RSS 订阅", render: "http", defaultIntervalMinutes: 60, llmHint: "" },
  { type: "app_store", label: "应用商店页", render: "browser", defaultIntervalMinutes: 1440, llmHint: "" },
];

// 常见页面的路径猜测，勾选后自动预填，用户可改
const PATH_GUESS: Record<string, string> = {
  homepage: "",
  pricing: "/pricing",
  changelog: "/changelog",
  blog: "/blog",
  docs: "/docs",
  status: "/status",
  rss: "/feed",
  app_store: "",
};

// 默认勾选：优先读账号偏好（设置页「添加竞品偏好」可配），否则只勾「官网首页」
const RECOMMENDED_TYPES = new Set<SourceType>(["pricing", "changelog"]);
/** 读取"新增竞品默认勾选的页面"偏好；无有效值时兜底为官网首页 */
function defaultSelectedTypes(): SourceType[] {
  const arr = preferences.defaultSourceTypes;
  return arr.length ? (arr as SourceType[]) : ["homepage"];
}

const typeOptions = ref<SourceTypeOption[]>([]);
const selected = ref<SourceType[]>([]);
const urls = reactive<Record<string, string>>({});
const intervals = reactive<Record<string, number>>({});

const rules: FormRules = {
  name: [{ required: true, message: "请输入竞品名称", trigger: "blur" }],
  officialUrl: [
    { required: true, message: "请输入官网地址", trigger: "blur" },
    {
      validator: (_rule, value: string, callback) => {
        const v = (value ?? "").trim();
        if (!v) return callback();
        const ok = /^(https?:\/\/)?[\w-]+(\.[\w-]+)+(:\d+)?([\w\-./?%&=:#]*)?$/.test(v);
        ok ? callback() : callback(new Error("请输入合法网址，如 https://notion.so"));
      },
      trigger: "blur",
    },
  ],
};

function normalizeBaseUrl(raw: string): string {
  const v = (raw ?? "").trim();
  if (!v) return "";
  return (/^https?:\/\//i.test(v) ? v : `https://${v}`).replace(/\/+$/, "");
}

const previewDomain = computed(
  () => normalizeBaseUrl(form.officialUrl).split("//")[1] ?? "",
);

function guessUrl(type: SourceType): string {
  const base = normalizeBaseUrl(form.officialUrl);
  if (!base) return "";
  // 只用「协议+主机」做页面猜测，避免官网带路径时重复拼接（如 x.com/pricing/pricing）
  const origin = base.match(/^https?:\/\/[^/]+/i)?.[0] ?? base;
  return origin + (PATH_GUESS[type] ?? "");
}

/** 页面的"有效网址"：用户填了就用它；若用户手动清空则视为空（不回退猜测）；否则按官网规则猜测 */
function effectiveUrl(type: SourceType): string {
  const typed = normalizeBaseUrl(urls[type] || "");
  if (typed) return typed;
  if (manualUrlEdited[type]) return "";
  return normalizeBaseUrl(guessUrl(type));
}

function labelOf(type: SourceType): string {
  return typeOptions.value.find((o) => o.type === type)?.label ?? type;
}

function humanize(minutes: number): string {
  if (!Number.isFinite(minutes)) return "—";
  if (minutes % 10080 === 0) {
    const n = minutes / 10080;
    return n === 1 ? "每周" : `每 ${n} 周`;
  }
  if (minutes % 1440 === 0) {
    const n = minutes / 1440;
    return n === 1 ? "每天" : `每 ${n} 天`;
  }
  if (minutes % 60 === 0) {
    const n = minutes / 60;
    return n === 1 ? "每小时" : `每 ${n} 小时`;
  }
  return `每 ${minutes} 分钟`;
}

function isSelected(type: SourceType): boolean {
  return selected.value.includes(type);
}

function removeType(type: SourceType) {
  // 暂存被取消勾选的页面（含网址与检测状态），重新勾选时原样恢复、保留“通过”
  removedCache[type] = {
    url: urls[type] ?? "",
    interval: intervals[type] ?? 0,
    state: checkState[type] ?? "",
    msg: checkMsg[type] ?? "",
    manual: !!manualUrlEdited[type],
  };
  selected.value = selected.value.filter((t) => t !== type);
  delete urls[type];
  delete intervals[type];
  delete checkState[type];
  delete checkMsg[type];
  delete manualUrlEdited[type];
}

function toggleType(opt: SourceTypeOption) {
  if (isSelected(opt.type)) {
    removeType(opt.type);
    return;
  }
  selected.value = [...selected.value, opt.type];
  const cached = removedCache[opt.type];
  if (cached) {
    // 重新勾选：优先恢复原样（保留“通过”状态与手动标记）
    const nextGuess = guessUrl(opt.type);
    if (!cached.manual && nextGuess && nextGuess !== cached.url) {
      // 非手填且官网已变动：跟随新官网重新猜测，旧“通过”作废
      urls[opt.type] = nextGuess;
      intervals[opt.type] = cached.interval;
      checkState[opt.type] = "";
      checkMsg[opt.type] = "";
    } else {
      // 手填，或官网未变：原样恢复（含已通过状态）
      urls[opt.type] = cached.url;
      intervals[opt.type] = cached.interval;
      checkState[opt.type] = cached.state;
      checkMsg[opt.type] = cached.msg;
      if (cached.manual) manualUrlEdited[opt.type] = true;
    }
    delete removedCache[opt.type];
  } else {
    // 官网已填 → 按本地规则自动补；官网没填 → 保持空白（不擅自做 AI 找址）
    urls[opt.type] = guessUrl(opt.type);
    intervals[opt.type] = opt.defaultIntervalMinutes ?? 1440;
  }
}

/** 用户没手填名称时，从官网域名猜一个品牌名 */
function guessNameFromUrl() {
  if (form.name.trim() || !previewDomain.value) return;
  const core = previewDomain.value.replace(/^www\./, "").split(".")[0];
  if (core) form.name = core.charAt(0).toUpperCase() + core.slice(1);
}

/** 官网地址变化后，同步刷新各监控页的预填地址并作废旧检测结果
 *  - 仅刷新"未被用户手动改过"的页面（让自动猜测跟随官网变动）；手动改过的页面原样保留，避免覆盖用户填写
 *  - 官网本身仅在"地址真的变了"时才作废状态；没变则保留，避免每次失焦都重复检测 */
let lastSyncedOfficial = "";
function syncUrlsWithOfficial() {
  selected.value.forEach((type) => {
    if (manualUrlEdited[type]) return; // 手动改过的页面保留，不随官网变动
    const next = guessUrl(type);
    if (urls[type] !== next) {
      // 仅当猜测地址真的变了才刷新并作废旧检测；地址没变则保留“通过”状态
      urls[type] = next;
      clearCheck(type);
    }
  });
  const current = normalizeBaseUrl(form.officialUrl);
  if (current !== lastSyncedOfficial) {
    clearCheck(OFFICIAL_KEY); // 官网地址变了才作废官网状态；没变则保留，失焦不会重复检测
    lastSyncedOfficial = current;
  }
}

/** 页面网址被用户手动编辑：作废旧检测结果，并标记为"手动改过"（官网变动时不再被自动猜测覆盖） */
function onPageUrlInput(type: SourceType) {
  clearCheck(type);
  manualUrlEdited[type] = true;
}

function onUrlBlur() {
  guessNameFromUrl();
  syncUrlsWithOfficial();
  // 手动填写/修改官网地址：失焦只对该网址自动检测可达性（不找页、不调 AI）
  void checkOne(OFFICIAL_KEY, form.officialUrl);
}

/** 智能检测填充 / 自动预填：一次完成「推断官网/分类 → 先检测已知页面 → 不通的再自动找页」
 *  - useAi=true（按钮 / 回车）：调用 AI 推断官网与分类（处理中文品牌名等复杂情况）；
 *  - useAi=false（用户自己填竞品时的失焦自动预填）：只用规则域名探测，不消耗 AI，分类留给用户。
 *  两种模式后续都走同一套「先检测、不通再找页」的非 AI 流程。
 */
let lastSuggestedName = "";
async function autoDetectFill(force = false, useAi = true) {
  const name = form.name.trim();
  if (!name) {
    if (force) ElMessage.warning("请先输入竞品名称");
    return;
  }
  if (!force && busy.value) return; // 自动预填不打断进行中的任务；按钮(force)可覆盖并取消旧任务
  if (!force && name === lastSuggestedName) return;
  lastSuggestedName = name;

  const token = ++runToken;
  runAbort?.abort(); // 取消上一次在途的批处理请求
  const ac = new AbortController();
  runAbort = ac;
  suggesting.value = true;
  smartFilling.value = force; // 只有点「智能检测填充」按钮(force)才让按钮转圈
  try {
    const filled: string[] = [];

    // 1) 名称 → 官网地址（useAi 时才用 AI 推断分类；否则只做规则域名探测）
    const r = await suggestCompetitor(name, categoryOptions, useAi, ac.signal);
    if (isRunCancelled(token)) return;
    const aiOfficial = normalizeBaseUrl(r.officialUrl || "");
    const currentOfficial = normalizeBaseUrl(form.officialUrl);
    if (aiOfficial && !currentOfficial) {
      // 官网还空 → 直接采用 AI 推断
      form.officialUrl = aiOfficial;
      syncUrlsWithOfficial();
      filled.push("官网地址");
    } else if (aiOfficial && aiOfficial !== currentOfficial) {
      // 已填官网与 AI 推断不同：先探一下现有的，不可达才改用 AI 的（避免覆盖正确的官网）
      await checkOne(OFFICIAL_KEY, form.officialUrl, ac.signal);
      if (isRunCancelled(token)) return;
      if (checkState[OFFICIAL_KEY] === "fail" && !checkUnverified[OFFICIAL_KEY]) {
        form.officialUrl = aiOfficial;
        syncUrlsWithOfficial();
        filled.push("官网地址（原地址不可达，已改用 AI 推断）");
      }
    }
    if (useAi && r.category && !form.category) {
      form.category = r.category;
      filled.push("分类");
    }

    // 2) 有了官网地址：先检测已知页面，不通的再自动找页（纯非 AI）
    let fixedCount = 0;
    const base = normalizeBaseUrl(form.officialUrl);
    if (!base) {
      await verifyUrls(() => isRunCancelled(token), ac.signal);
      if (isRunCancelled(token)) return;
    } else {
      [fixedCount] = await detectAndFindPages(base, token, ac.signal);
      if (isRunCancelled(token)) return;
      if (fixedCount) filled.push(`自动修正 ${fixedCount} 个页面`);
    }
    // 只提示"AI 也没找到 / 仍不可达"的页面；已修好的不再打扰
    const remaining = collectRemainingProblems();
    notifyFails(remaining);

    if (filled.length) ElMessage.success(`已自动填入：${filled.join("、")}`);
    else if (!remaining.length && r.message) ElMessage.info(r.message);
  } catch {
    if (isRunCancelled(token)) return;
    if (force) ElMessage.error("智能检测填充失败，请稍后重试");
  } finally {
    if (runAbort === ac) runAbort = null;
    if (!isRunCancelled(token)) {
      suggesting.value = false;
      smartFilling.value = false;
    }
  }
}

/** 把"仍未能解决"的清单以通知形式提示（无则不打扰），并提供"一键重新寻找"入口 */
function notifyFails(fails: string[]) {
  if (!fails.length) return;
  const notice = ElNotification({
    title: "部分页面未能确认可用地址",
    type: "warning",
    duration: 10000,
    message: h("div", { style: "line-height:1.7" }, [
      ...fails.map((l) => h("div", `· ${l}`)),
      h(
        "div",
        { style: "margin-top:6px;color:#909399;font-size:12px" },
        "请手动填写正确地址，或点下方按钮再让 AI 找一次。",
      ),
      h(
        "div",
        { style: "margin-top:8px" },
        h(
          "button",
          {
            style:
              "padding:2px 10px;border:1px solid var(--el-color-primary);color:var(--el-color-primary);background:transparent;border-radius:4px;cursor:pointer;font-size:12px",
            onClick: () => {
              notice.close();
              void refindAll();
            },
          },
          "一键重新寻找",
        ),
      ),
    ]),
  });
}

/** 先检测已知页面，再对"不通"的已勾选监控页自动寻找更可能正确的地址。
 *  返回 [自动修正的页面数, 仍未解决的清单]；被取消时返回 [0, []]。 */
async function detectAndFindPages(
  base: string,
  token: number,
  signal?: AbortSignal,
): Promise<[number, string[]]> {
  await verifyUrls(() => isRunCancelled(token), signal);
  if (isRunCancelled(token)) return [0, []];

  // 对"未通过"或"空白未填"的已勾选监控页，再去自动寻找更可能正确的地址：
  //  - "检测网址"那一遍已把【有值但未通过】的标成 fail；
  //  - 【空白未填】的没有值可测，停留未检测态，同样需要 AI 来补。两者都纳入寻找。
  // 逐页寻找（每次只扫该类型），以便像"重新寻找"一样展示 x/y 进度与行内结果。
  const needFind = selected.value.filter((t) => checkState[t] !== "ok");
  if (!needFind.length) return [0, collectRemainingProblems()];

  const allTypes = typeOptions.value.map((o) => o.type);
  checkProgress.total = needFind.length;
  checkProgress.done = 0;
  refinding.value = true;
  let fixedCount = 0;
  try {
    for (const type of needFind) {
      if (isRunCancelled(token)) return [0, []];
      refindingType.value = type;
      refindResult[type] = "";
      try {
        const skipTypes = allTypes.filter((t) => t !== type);
        const res = await discoverSources(base, skipTypes, signal);
        if (isRunCancelled(token)) return [0, []];
        const hit = res.sources.find((x) => x.sourceType === type && x.found && x.url);
        if (hit && isSelected(type)) {
          urls[type] = hit.url as string;
          manualUrlEdited[type] = true; // 已确认的好地址：官网变动不再被猜测覆盖
          applyCheckResult(
            type,
            urls[type],
            true,
            hit.httpStatus ? `自动寻找已校验（HTTP ${hit.httpStatus}）` : "自动寻找已校验",
          );
          fixedCount += 1;
          refindResult[type] = "found";
        } else {
          refindResult[type] = "miss"; // AI 也没找到
        }
      } catch {
        if (isRunCancelled(token)) return [0, []];
        refindResult[type] = "miss"; // 单页失败不阻断其余
      } finally {
        checkProgress.done += 1;
        refindingType.value = null;
      }
    }
  } finally {
    refinding.value = false;
    refindingType.value = null;
  }
  // 只回报"AI 也没找到 / 仍不可达"的页面，已修好的不再提示
  return [fixedCount, collectRemainingProblems()];
}

/** 对指定页面「重新寻找」：只扫描这些类型，再让 AI/规则找一次更可能正确的地址 */
async function refindPages(types: SourceType[]) {
  if (locked.value || !types.length) return;
  const base = normalizeBaseUrl(form.officialUrl);
  if (!base) {
    ElMessage.warning("请先填写官网地址");
    return;
  }
  const token = ++runToken;
  runAbort?.abort();
  const ac = new AbortController();
  runAbort = ac;
  suggesting.value = true; // 复用运行态：锁表单 + 可取消
  refinding.value = true;
  checkProgress.total = types.length;
  checkProgress.done = 0;
  try {
    const allTypes = typeOptions.value.map((o) => o.type);
    let fixed = 0;
    // 逐页寻找（每次只扫该类型），以便展示 x/y 进度
    for (const type of types) {
      if (isRunCancelled(token)) return;
      refindingType.value = type;
      refindResult[type] = "";
      try {
        const skipTypes = allTypes.filter((t) => t !== type);
        const res = await discoverSources(base, skipTypes, ac.signal);
        if (isRunCancelled(token)) return;
        const hit = res.sources.find((x) => x.sourceType === type && x.found && x.url);
        if (hit && isSelected(type)) {
          urls[type] = hit.url as string;
          manualUrlEdited[type] = true; // 已确认的好地址：官网变动不再被猜测覆盖
          applyCheckResult(
            type,
            urls[type],
            true,
            hit.httpStatus ? `自动寻找已校验（HTTP ${hit.httpStatus}）` : "自动寻找已校验",
          );
          fixed += 1;
          refindResult[type] = "found";
        } else {
          refindResult[type] = "miss";
        }
      } catch {
        if (isRunCancelled(token)) return;
        refindResult[type] = "miss"; // 单页失败不阻断其余
      } finally {
        checkProgress.done += 1;
        refindingType.value = null;
      }
    }
    if (types.length === 1) {
      if (fixed) ElMessage.success(`${labelOf(types[0])}：已找到并校验`);
      else ElMessage.warning(`${labelOf(types[0])}：仍未找到，请手动填写地址`);
    } else {
      const miss = types.length - fixed;
      if (fixed && miss) {
        ElMessage.warning(`已为 ${fixed} 个页面找到地址；仍有 ${miss} 个未找到，请手动填写`);
      } else if (fixed) {
        ElMessage.success(`已为 ${fixed} 个页面找到并校验地址`);
      } else {
        ElMessage.warning(`仍未找到地址，请手动填写`);
      }
    }
  } catch {
    if (isRunCancelled(token)) return;
    ElMessage.error("重新寻找失败，请稍后重试");
  } finally {
    refinding.value = false;
    refindingType.value = null;
    if (runAbort === ac) runAbort = null;
    if (!isRunCancelled(token)) suggesting.value = false;
  }
}

/** 单页「重新寻找」 */
function refindOne(type: SourceType) {
  void refindPages([type]);
}

/** 一键对所有"仍未解决"的页面重新寻找 */
function refindAll() {
  const targets = selected.value.filter(
    (t) => checkState[t] === "fail" || checkUnverified[t],
  );
  if (!targets.length) {
    ElMessage.info("没有需要重新寻找的页面");
    return;
  }
  void refindPages(targets);
}

/** 名称失焦：仅按【本地默认规则】预填各字段，不发任何请求、不做连通性检测、不调 AI。
 *  规则：官网 = https://<名称>.com（小写、去空格）；页面地址 = 官网 + 常规路径。
 *  仅对纯英文/数字/点/连字符的名称套用（中文等无法可靠映射成域名，不生成无效网址，留空手动填）。
 *  若官网还空、或仍是上一次同名规则填的值（说明用户没手动改过），才用新规则覆盖。 */
function prefillByRule() {
  const name = form.name.trim();
  if (!name) return;
  if (name === lastSuggestedName) return;

  const slug = name.toLowerCase().replace(/\s+/g, "");
  // 非 ASCII（含中文）名称无法可靠拼出官网域名，跳过规则预填，避免产生 https://豆包.com 这类无效地址
  if (!/^[a-z0-9.-]+$/.test(slug)) return;

  const rule = `https://${slug}.com`;
  const prevRule = lastSuggestedName
    ? `https://${lastSuggestedName.toLowerCase().replace(/\s+/g, "")}.com`
    : "";
  if (!form.officialUrl.trim() || form.officialUrl.trim() === prevRule) {
    form.officialUrl = rule;
    syncUrlsWithOfficial(); // 按规则给首页/定价/更新日志等填充猜测地址并清空检测状态
  }
  lastSuggestedName = name;
}

function onNameBlur() {
  prefillByRule();
}

async function loadTypeOptions() {
  if (typeOptions.value.length) return;
  try {
    const list = await fetchSourceTypes();
    typeOptions.value = list.length ? list : FALLBACK_TYPES;
  } catch {
    typeOptions.value = FALLBACK_TYPES;
  }
}

function resetForm() {
  formRef.value?.clearValidate();
  lastSuggestedName = ""; // 重新打开弹窗后允许再次自动填充
  Object.assign(form, { name: "", officialUrl: "", category: "", description: "" });
  selected.value = [];
  Object.keys(urls).forEach((key) => delete urls[key]);
  Object.keys(intervals).forEach((key) => delete intervals[key]);
  Object.keys(checkState).forEach((key) => delete checkState[key]);
  Object.keys(checkMsg).forEach((key) => delete checkMsg[key]);
  Object.keys(checkUnverified).forEach((key) => delete checkUnverified[key]);
  Object.keys(checkRun).forEach((key) => delete checkRun[key]);
  Object.keys(manualUrlEdited).forEach((key) => delete manualUrlEdited[key]);
  Object.keys(removedCache).forEach((key) => delete removedCache[key]);
  lastSyncedOfficial = "";
  // 注意：allowUnreachableOfficial 不清空——它是全局偏好，跨弹窗记忆
  runAbort?.abort();
  runAbort = null;
  submitting.value = false;
}

function applyDefaults() {
  defaultSelectedTypes().forEach((type) => {
    const opt = typeOptions.value.find((o) => o.type === type);
    if (!opt) return;
    selected.value.push(type);
    urls[type] = "";
    intervals[type] = opt.defaultIntervalMinutes ?? 1440;
  });
}

/** 编辑模式：用已有竞品及其监控源回填表单 */
function applyCompetitor(item: CompetitorItem) {
  form.name = item.name ?? "";
  form.officialUrl = item.domain ?? "";
  form.category = item.category ?? "";
  form.description = item.desc ?? "";
  (item.sources ?? []).forEach((source) => {
    if (selected.value.includes(source.sourceType)) return;
    selected.value.push(source.sourceType);
    urls[source.sourceType] = source.url;
    intervals[source.sourceType] = source.intervalMinutes;
    manualUrlEdited[source.sourceType] = true; // 编辑回填的既有网址视为"已确认"，官网变动不覆盖
  });
}

async function initialize() {
  resetForm();
  // 偏好跟账号走：store 已加载过就是最新值（设置页改完会同步到这个 store）
  await preferences.ensureLoaded();
  await loadTypeOptions();
  if (props.competitor) {
    applyCompetitor(props.competitor);
    if (!selected.value.length) applyDefaults(); // 历史数据可能没有监控源，兜底
  } else {
    applyDefaults();
  }
}

watch(
  visible,
  (open) => {
    if (open) {
      initialize();
    } else {
      // 关闭弹窗：中止在途请求，避免请求回来后改写已重置的状态
      runAbort?.abort();
      runAbort = null;
    }
  },
  { immediate: true },
);

function buildPayload(skipTypes: Set<string> = new Set()): CompetitorCreatePayload {
  const sources: MonitorSourceInput[] = selected.value
    .filter((type) => !skipTypes.has(type))
    .map((type) => ({
      sourceType: type,
      url: effectiveUrl(type) || undefined,
      intervalMinutes: intervals[type],
    }));
  return {
    name: form.name.trim(),
    officialUrl: normalizeBaseUrl(form.officialUrl),
    category: form.category || undefined,
    description: form.description.trim() || undefined,
    sources,
  };
}

/** 收集待检测的网址：官网首页 + 各勾选页面（同址的会在检测时自动去重请求） */
function buildVerifyTargets(): { key: string; label: string; url: string }[] {
  const targets: { key: string; label: string; url: string }[] = [];
  const official = normalizeBaseUrl(form.officialUrl);
  if (official) targets.push({ key: OFFICIAL_KEY, label: "官网首页", url: official });
  for (const type of selected.value) {
    const url = effectiveUrl(type);
    if (url) targets.push({ key: type, label: labelOf(type), url });
  }
  return targets;
}

function escapeHtml(s: string): string {
  return s.replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]!,
  );
}

/** 把若干行文案拼成带样式的 HTML（弹窗用），每行做转义防注入 */
function toHtmlList(lines: string[]): string {
  return lines.map((l) => `· ${escapeHtml(l)}`).join("<br>");
}

/** 保存前批量校验网址可达性，返回逐项结果；同时把行内状态点亮
 *  - 已经检测通过（打勾）的页面不重复检查，保留其状态
 *  - 同一网址（如「官网首页」与「官网地址」通常同址）只探测一次
 */
async function verifyUrls(
  isCancelled: () => boolean = () => false,
  signal?: AbortSignal,
): Promise<
  { key: string; label: string; url: string; ok: boolean; message: string; unverified: boolean }[]
> {
  const targets = buildVerifyTargets().filter((t) => checkState[t.key] !== "ok");
  targets.forEach((t) => {
    checkRun[t.key] = (checkRun[t.key] ?? 0) + 1; // 作废可能存在的在途单字段检测
    checkState[t.key] = "checking";
    checkMsg[t.key] = "";
    checkUnverified[t.key] = false;
  });

  // 同一网址（如「官网首页」与「官网地址」通常同址）只发一次请求，结果复用
  const uniqueUrls = [...new Set(targets.map((t) => t.url).filter(Boolean))];
  checkProgress.total = uniqueUrls.length;
  checkProgress.done = 0;
  const byUrl = new Map<string, { ok: boolean; message: string; unverified: boolean }>();
  await Promise.all(
    uniqueUrls.map(async (url) => {
      if (isCancelled()) return;
      try {
        const r = await checkSourceUrl(url, signal);
        if (isCancelled()) return;
        byUrl.set(url, { ok: r.ok, message: r.message, unverified: false });
      } catch {
        // 请求失败 → 无法判定（不算"未通过"），不参与硬拦截
        byUrl.set(url, { ok: false, message: "未能校验（请求失败，请稍后重试）", unverified: true });
      } finally {
        checkProgress.done += 1;
      }
    }),
  );

  // 被取消：清掉还停在"检测中"的行内状态，避免留下转圈图标
  if (isCancelled()) {
    targets.forEach((t) => {
      if (checkState[t.key] === "checking") clearCheck(t.key);
    });
    return [];
  }

  return targets.map((t) => {
    const r =
      byUrl.get(t.url) ?? { ok: false, message: "未能校验（请求失败，请稍后重试）", unverified: true };
    checkState[t.key] = r.ok ? "ok" : "fail";
    checkMsg[t.key] = r.message;
    checkUnverified[t.key] = r.unverified;
    return { ...t, ...r };
  });
}

/** 单个网址的自动检测（输入框失焦触发）：只更新相关行状态
 *  - 带令牌防竞态：请求期间用户改了这个输入框（clearCheck 会自增令牌）→ 结果作废，不覆盖新值
 *  - 同一网址（如「官网地址」与「官网首页」通常同址）的状态一并同步，避免图标不一致 */
async function checkOne(key: string, raw: string, signal?: AbortSignal) {
  const url = normalizeBaseUrl(raw || "");
  if (!url) {
    clearCheck(key);
    return;
  }
  if (checkState[key] === "ok") return; // 已通过且未改动，不重复检测
  const myToken = (checkRun[key] ?? 0) + 1;
  checkRun[key] = myToken;
  checkState[key] = "checking";
  checkMsg[key] = "";
  checkUnverified[key] = false;
  let ok = false;
  let message = "";
  let unverified = false;
  try {
    const r = await checkSourceUrl(url, signal);
    ok = r.ok;
    message = r.message;
  } catch {
    ok = false;
    unverified = true;
    message = "未能校验（请求失败，请稍后重试）";
  }
  if (checkRun[key] !== myToken) return; // 期间该字段被编辑/清除 → 丢弃旧结果
  applyCheckResult(key, url, ok, message, unverified);
}

/** 写入检测结论，并把同一网址的其它行（含官网同址）一起点亮，保持状态一致 */
function applyCheckResult(
  key: string,
  url: string,
  ok: boolean,
  message: string,
  unverified = false,
) {
  checkState[key] = ok ? "ok" : "fail";
  checkMsg[key] = message;
  checkUnverified[key] = unverified;
  const others = [OFFICIAL_KEY, ...selected.value].filter((k) => k !== key);
  for (const k of others) {
    if (checkState[k] === "checking") continue; // 正在检测的行不覆盖
    const ku =
      k === OFFICIAL_KEY
        ? normalizeBaseUrl(form.officialUrl)
        : effectiveUrl(k as SourceType);
    if (ku && ku === url) {
      checkState[k] = ok ? "ok" : "fail";
      checkMsg[k] = message;
      checkUnverified[k] = unverified;
    }
  }
}

/** 把检测结果按「网址」去重后整理成可读的失败清单（同址只报一次；不含"未能校验"） */
function collectFailLines(
  results: { label: string; url: string; ok: boolean; message: string; unverified?: boolean }[],
): string[] {
  const seen = new Set<string>();
  const lines: string[] = [];
  for (const r of results) {
    if (r.ok || r.unverified || seen.has(r.url)) continue;
    seen.add(r.url);
    lines.push(`${r.label}：${r.message}`);
  }
  return lines;
}

/** 未能校验（请求失败/超时）的清单：仅作提示，不作为硬拦截依据 */
function collectUnverifiedLines(
  results: { label: string; url: string; ok: boolean; message: string; unverified?: boolean }[],
): string[] {
  const seen = new Set<string>();
  const lines: string[] = [];
  for (const r of results) {
    if (!r.unverified || seen.has(r.url)) continue;
    seen.add(r.url);
    lines.push(`${r.label}：${r.message}`);
  }
  return lines;
}

/** 当前仍未解决（未通过或未能校验）的已勾选页面清单 */
function collectRemainingProblems(): string[] {
  return selected.value
    .filter((t) => checkState[t] === "fail" || checkUnverified[t])
    .map((t) => `${labelOf(t)}：${checkMsg[t] || "无法访问"}`);
}

/** 「检测网址」按钮：手动探一次，结果以行内图标 + 通知呈现，不阻断保存 */
async function runManualCheck() {
  if (busy.value || submitting.value) return;
  // 先处理"已勾选但网址还是空白"的页面：提示待填并中止（未勾选的一律不理会）
  const blankTypes = selected.value.filter((t) => !effectiveUrl(t));
  if (blankTypes.length) {
    ElMessage.warning(
      `以下已勾选页面还没有网址，请先填写：${blankTypes.map((t) => labelOf(t)).join("、")}`,
    );
    return;
  }
  const all = buildVerifyTargets();
  const skipped = all.filter((t) => checkState[t.key] === "ok").length;
  if (all.length && skipped === all.length) {
    ElMessage.info("已检测通过的页面无需重复检查");
    return;
  }
  const token = ++runToken;
  runAbort?.abort();
  const ac = new AbortController();
  runAbort = ac;
  manualChecking.value = true;
  try {
    const results = await verifyUrls(() => isRunCancelled(token), ac.signal); // 内部会自动跳过已通过的
    if (isRunCancelled(token)) return;
    const fails = collectFailLines(results);
    const unverified = collectUnverifiedLines(results);
    if (fails.length) {
      ElNotification({
        title: "部分页面可能无法访问",
        type: "warning",
        duration: 6000,
        dangerouslyUseHTMLString: true,
        message:
          toHtmlList(fails) +
          (unverified.length ? `<br><br>另有 ${unverified.length} 个网址未能校验（请求失败）` : ""),
      });
    } else if (unverified.length) {
      ElMessage.warning(`有 ${unverified.length} 个网址未能校验（请求失败），请稍后重试`);
    } else {
      ElMessage.success(
        skipped ? `检查完成，已跳过 ${skipped} 个已通过的页面` : "所有页面均可正常访问",
      );
    }
  } finally {
    if (runAbort === ac) runAbort = null;
    if (!isRunCancelled(token)) manualChecking.value = false;
  }
}

/** 查重：同名或同官网的既有竞品（编辑时排除自身） */
function findDuplicateCompetitor(): CompetitorItem | null {
  const name = form.name.trim().toLowerCase();
  const domain = normalizeBaseUrl(form.officialUrl).toLowerCase();
  const selfId = props.competitor?.id;
  const list = (store.competitors ?? []) as CompetitorItem[];
  for (const c of list) {
    if (selfId && c.id === selfId) continue;
    const cName = (c.name ?? "").trim().toLowerCase();
    const cDomain = normalizeBaseUrl(c.domain ?? "").toLowerCase();
    if ((domain && cDomain && cDomain === domain) || (name && cName && cName === name)) {
      return c;
    }
  }
  return null;
}

async function handleSubmit() {
  if (busy.value || submitting.value) return;
  const valid = await formRef.value?.validate().catch(() => false);
  if (!valid) return;

  // 至少保留一个监控页面
  if (!selected.value.length) {
    ElMessage.warning("请至少勾选一个监控页面");
    return;
  }

  // 重复竞品提示（同名或同官网）
  const dup = findDuplicateCompetitor();
  if (dup) {
    ElMessage.warning(`已存在相同名称或官网的竞品「${dup.name}」，请勿重复创建`);
    return;
  }

  submitting.value = true;
  try {
    // 已勾选但网址空白 → 提示待填，不保存（与「检测网址」口径一致）
    const blankTypes = selected.value.filter((t) => !effectiveUrl(t));
    if (blankTypes.length) {
      ElMessage.warning(
        `以下已勾选页面还没有网址，请先填写：${blankTypes.map((t) => labelOf(t)).join("、")}`,
      );
      return;
    }

    // 校验可达性（跳过已通过）：
    //  - 官网地址"确认不可达" → 硬拦截（关键）；
    //  - 可选监控页"确认不可达" → 新建时跳过该页、编辑时保留原配置，均不阻断；
    //  - "未能校验(请求失败)" → 只提示不阻断。
    const results = await verifyUrls();
    const officialBad = checkState[OFFICIAL_KEY] === "fail" && !checkUnverified[OFFICIAL_KEY];
    if (officialBad && !allowUnreachableOfficial.value) {
      ElMessage.warning(
        `官网地址无法访问（${checkMsg[OFFICIAL_KEY] || "未通过"}），请先修正后再保存`,
      );
      return;
    }
    if (officialBad) {
      ElMessage.warning("官网地址当前不可访问，将先创建，请稍后在详情中修正");
    }
    const unverified = collectUnverifiedLines(results);
    if (unverified.length) {
      ElMessage.warning(`有 ${unverified.length} 个网址未能校验（请求失败），已跳过校验`);
    }
    const officialUrl = normalizeBaseUrl(form.officialUrl);
    const pageBad = selected.value.filter(
      (t) =>
        checkState[t] === "fail" &&
        !checkUnverified[t] &&
        normalizeBaseUrl(effectiveUrl(t)) !== officialUrl, // 与官网同址的页随官网一起保留
    );

    if (props.competitor) {
      // 编辑：不可达的可选页交给用户选择——移除 or 保留原配置
      let removeBad = false;
      if (pageBad.length) {
        removeBad = await ElMessageBox.confirm(
          `<div style="line-height:1.7">以下监控页当前无法访问，是否从该竞品中移除？<br><br>${toHtmlList(
            pageBad.map((t) => `${labelOf(t)}：${checkMsg[t] || "无法访问"}`),
          )}</div>`,
          "监控页不可访问",
          {
            type: "warning",
            confirmButtonText: "移除这些页",
            cancelButtonText: "保留",
            dangerouslyUseHTMLString: true,
          },
        )
          .then(() => true)
          .catch(() => false);
      }
      const payload = buildPayload(removeBad ? new Set<string>(pageBad) : new Set<string>());
      await store.editCompetitor(props.competitor.id, payload);
      ElMessage.success("修改已保存");
      if (removeBad && pageBad.length) {
        ElMessage.info(`已移除 ${pageBad.length} 个不可访问的监控页`);
      }
    } else {
      // 新建：跳过不可达的可选页（不写入失败地址），不阻断保存
      const payload = buildPayload(new Set<string>(pageBad));
      await store.addCompetitor(payload);
      ElMessage.success("竞品已添加，开始监控");
      if (pageBad.length) {
        ElMessage.info(
          `有 ${pageBad.length} 个页面创建时无法访问，已跳过：${pageBad.map((t) => labelOf(t)).join("、")}，可稍后在详情中补充`,
        );
      }
    }
    visible.value = false;
  } catch {
    ElMessage.error("保存失败，请稍后重试");
  } finally {
    submitting.value = false;
  }
}

const footerTip = computed(() => {
  if (busy.value) {
    if (refinding.value) {
      const rp = checkProgress.total ? `（${checkProgress.done}/${checkProgress.total}）` : "";
      return `正在重新寻找${rp}，可点「取消」打断`;
    }
    const p = checkProgress.total ? `（检测中 ${checkProgress.done}/${checkProgress.total}）` : "";
    return `正在自动填充 / 检测${p}，可点「取消」打断`;
  }
  return isEdit.value
    ? `保存后按此配置同步监控源（共 ${selected.value.length || 1} 个）`
    : `将创建 ${selected.value.length || 1} 个监控源，可稍后在详情中调整`;
});
</script>

<template>
  <el-dialog
    v-model="visible"
    :title="isEdit ? '编辑竞品' : '新增竞品'"
    width="min(720px, 92vw)"
    :close-on-click-modal="false"
    :close-on-press-escape="!locked"
    :show-close="!locked"
    class="competitor-dialog"
  >
    <el-form
      ref="formRef"
      :model="form"
      :rules="rules"
      label-position="top"
      class="dialog-form"
    >
      <div class="section-title">品牌信息</div>

      <div class="brand-row">
        <div class="brand-fields">
          <el-form-item label="竞品名称" prop="name" class="flex-1">
            <el-input
              v-model="form.name"
              placeholder="如 Notion，填完自动预填；或回车/点按钮用 AI 检测"
              maxlength="100"
              clearable
              :disabled="locked"
              @blur="onNameBlur"
              @keyup.enter="autoDetectFill(true)"
            >
              <template #append>
                <el-button
                  class="smart-fill-btn"
                  type="primary"
                  :loading="smartFilling"
                  :disabled="locked"
                  @click="autoDetectFill(true)"
                >
                  <el-icon v-if="!suggesting"><MagicStick /></el-icon>
                  智能检测填充
                </el-button>
              </template>
            </el-input>
          </el-form-item>
          <el-form-item label="官网地址" prop="officialUrl" class="flex-1">
            <el-input
              v-model="form.officialUrl"
              placeholder="如 https://notion.so"
              clearable
              :prefix-icon="Link"
              :disabled="locked"
              @input="clearCheck(OFFICIAL_KEY)"
              @blur="onUrlBlur"
            >
              <template #suffix>
                <el-tooltip v-if="checkUnverified[OFFICIAL_KEY]" :content="checkMsg[OFFICIAL_KEY]" placement="top">
                  <el-icon color="var(--el-color-info)"><InfoFilled /></el-icon>
                </el-tooltip>
                <el-tooltip v-else-if="checkState[OFFICIAL_KEY] === 'fail'" :content="checkMsg[OFFICIAL_KEY]" placement="top">
                  <el-icon color="var(--el-color-warning)"><WarningFilled /></el-icon>
                </el-tooltip>
                <el-icon v-else-if="checkState[OFFICIAL_KEY] === 'ok'" color="var(--el-color-success)"><Check /></el-icon>
                <el-icon v-else-if="checkState[OFFICIAL_KEY] === 'checking'" class="spin"><Loading /></el-icon>
              </template>
            </el-input>
            <div
              v-if="form.name.trim() && !form.officialUrl.trim() && !locked"
              class="field-hint"
            >
              没自动识别到官网？点上方「智能检测填充」用 AI 帮你查找
            </div>
            <div
              v-if="checkState[OFFICIAL_KEY] === 'fail' && !checkUnverified[OFFICIAL_KEY] && !locked"
              class="field-hint"
            >
              <el-checkbox v-model="allowUnreachableOfficial">
                官网暂时不可达也先创建（稍后可在详情中修正）
              </el-checkbox>
            </div>
          </el-form-item>
        </div>
      </div>

      <div class="two-col">
        <el-form-item label="分类" prop="category" class="flex-1">
          <el-select
            v-model="form.category"
            placeholder="选择或输入分类"
            filterable
            allow-create
            default-first-option
            clearable
            :disabled="locked"
            class="full-width"
          >
            <el-option
              v-for="c in categoryOptions"
              :key="c"
              :label="c"
              :value="c"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="一句话描述" prop="description" class="flex-1">
          <el-input
            v-model="form.description"
            placeholder="它是什么、和你的差异点"
            maxlength="120"
            show-word-limit
            clearable
            :disabled="locked"
          />
        </el-form-item>
      </div>

      <div class="section-title">
        监控页面
        <span class="section-hint">勾选要持续对比的页面，频率已按类型预置</span>
      </div>

      <div class="type-grid">
        <button
          v-for="opt in typeOptions"
          :key="opt.type"
          type="button"
          class="type-card"
          :class="{ active: isSelected(opt.type) }"
          :disabled="locked"
          @click="toggleType(opt)"
        >
          <span class="type-label">
            {{ opt.label }}
            <em
              v-if="RECOMMENDED_TYPES.has(opt.type) && !isSelected(opt.type)"
              class="type-rec"
            >推荐</em>
          </span>
          <span class="type-meta">
            {{ opt.render === "browser" ? "浏览器渲染" : "直接抓取" }} ·
            {{ humanize(opt.defaultIntervalMinutes) }}
          </span>
          <el-icon v-if="isSelected(opt.type)" class="type-check">
            <Check />
          </el-icon>
        </button>
      </div>

      <div v-if="selected.length" class="source-list">
        <div v-for="type in selected" :key="type" class="source-row">
          <span class="source-name">{{ labelOf(type) }}</span>
          <el-input
            v-model="urls[type]"
            size="small"
            placeholder="页面地址"
            class="source-url"
            :disabled="locked"
            @input="onPageUrlInput(type)"
            @blur="checkOne(type, urls[type])"
          >
            <template #suffix>
              <span
                v-if="!checkState[type] && !manualUrlEdited[type] && effectiveUrl(type)"
                class="verify-hint"
                title="按官网规则猜测的地址，尚未验证"
              >待验证</span>
              <el-tooltip v-if="checkUnverified[type]" :content="checkMsg[type]" placement="top">
                <el-icon color="var(--el-color-info)"><InfoFilled /></el-icon>
              </el-tooltip>
              <el-tooltip v-else-if="checkState[type] === 'fail'" :content="checkMsg[type]" placement="top">
                <el-icon color="var(--el-color-warning)"><WarningFilled /></el-icon>
              </el-tooltip>
              <el-icon v-else-if="checkState[type] === 'ok'" color="var(--el-color-success)"><Check /></el-icon>
              <el-icon v-else-if="checkState[type] === 'checking'" class="spin"><Loading /></el-icon>
            </template>
          </el-input>
          <span v-if="refindResult[type] === 'found'" class="re-hint ok">已找到</span>
          <span v-else-if="refindResult[type] === 'miss'" class="re-hint miss">未找到，请手动填写</span>
          <span class="row-action">
            <el-button
              v-if="refindingType === type"
              link
              type="primary"
              size="small"
              loading
            >寻找中</el-button>
            <el-button
              v-else-if="checkUnverified[type]"
              link
              type="primary"
              size="small"
              :disabled="locked"
              @click="checkOne(type, urls[type])"
            >重试</el-button>
            <el-button
              v-else-if="checkState[type] === 'fail'"
              link
              type="primary"
              size="small"
              :disabled="locked"
              @click="refindOne(type)"
            >重新寻找</el-button>
          </span>
          <el-select v-model="intervals[type]" size="small" class="source-interval" :disabled="locked">
            <el-option
              v-for="choice in INTERVAL_CHOICES"
              :key="choice.value"
              :label="choice.label"
              :value="choice.value"
            />
          </el-select>
          <el-button
            link
            type="danger"
            :icon="Delete"
            :disabled="locked"
            @click="removeType(type)"
          />
        </div>
      </div>
      <div v-else class="source-empty">
        <el-icon><InfoFilled /></el-icon>
        未勾选页面，将默认为「官网首页」创建一个监控源
      </div>
    </el-form>

    <template #footer>
      <div class="dialog-footer">
        <span class="footer-tip">{{ footerTip }}</span>
        <div class="footer-actions">
          <template v-if="busy">
            <el-button @click="cancelRun">取消</el-button>
          </template>
          <template v-else>
            <el-button :disabled="locked" @click="visible = false">取消</el-button>
            <el-button :disabled="locked" @click="runManualCheck">检测网址</el-button>
            <el-button v-if="hasUnresolved" :disabled="locked" @click="refindAll">重新寻找全部</el-button>
            <el-button type="primary" :loading="submitting" :disabled="locked" @click="handleSubmit">
              {{ isEdit ? "保存修改" : "立即创建" }}
            </el-button>
          </template>
        </div>
      </div>
    </template>
  </el-dialog>
</template>

<style scoped>
.dialog-form {
  max-height: 62vh;
  overflow-y: auto;
  padding-right: 0.4vw;
}

.section-title {
  display: flex;
  align-items: baseline;
  gap: 0.6vw;
  font-size: 1vmax;
  font-weight: 600;
  color: var(--app-text-color-primary);
  margin: 0.4vh 0 1.4vh;
  padding-left: 0.6vw;
  border-left: 3px solid var(--app-color-primary);
}
.section-hint {
  font-size: 0.8vmax;
  font-weight: 400;
  color: var(--app-text-color-placeholder);
}

/* 品牌信息 */
.brand-row {
  display: flex;
  align-items: flex-start;
  gap: 1vw;
  margin-bottom: 0.6vh;
}
.brand-fields {
  flex: 1;
  display: flex;
  gap: 1vw;
}
.flex-1 {
  flex: 1;
  min-width: 0;
}
/* 智能检测填充按钮：高亮醒目、一目了然可点击 */
.smart-fill-btn.el-button {
  border: none;
  background: linear-gradient(135deg, #409eff 0%, #6c5ce7 100%);
  color: #fff;
  font-weight: 600;
  letter-spacing: 0.5px;
  box-shadow: 0 2px 8px rgba(108, 92, 231, 0.4);
  transition: transform 0.15s ease, box-shadow 0.15s ease, background 0.15s ease;
}
.smart-fill-btn.el-button:hover:not(:disabled) {
  background: linear-gradient(135deg, #5aabff 0%, #8474f0 100%);
  box-shadow: 0 4px 14px rgba(108, 92, 231, 0.55);
  transform: translateY(-1px);
}
.smart-fill-btn.el-button:active:not(:disabled) {
  transform: translateY(0);
}
.smart-fill-btn.el-button:disabled {
  background: linear-gradient(135deg, #a9c8f5 0%, #c3b8f0 100%);
  box-shadow: none;
}
.two-col {
  display: flex;
  gap: 1vw;
}
.full-width {
  width: 100%;
}

/* 监控页面卡片 */
.type-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
  gap: 0.8vw;
  margin-bottom: 1.6vh;
}
.type-card {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 0.4vh;
  padding: 1vh 0.8vw;
  text-align: left;
  cursor: pointer;
  background: var(--app-color-blue-light-5);
  border: 1px solid transparent;
  border-radius: 0.8vmax;
  transition: all 0.18s ease;
  font-family: inherit;
}
.type-card:hover {
  border-color: var(--app-color-blue-light-3);
  transform: translateY(-1px);
}
.type-card.active {
  background: var(--app-color-blue-light-4);
  border-color: var(--app-color-primary);
}
.type-label {
  font-size: 0.92vmax;
  font-weight: 600;
  color: var(--app-text-color-primary);
}
.type-meta {
  font-size: 0.75vmax;
  color: var(--app-text-color-placeholder);
}
.type-rec {
  margin-left: 0.3vw;
  padding: 0 0.3vw;
  font-size: 0.66vmax;
  font-style: normal;
  font-weight: 500;
  color: var(--app-color-primary);
  background: color-mix(in srgb, var(--app-color-primary) 12%, transparent);
  border-radius: 0.3vw;
}
.verify-hint {
  font-size: 0.72vmax;
  color: var(--app-text-color-placeholder);
  white-space: nowrap;
}
.re-hint {
  font-size: 0.72vmax;
  white-space: nowrap;
}
.re-hint.ok {
  color: var(--el-color-success);
}
.re-hint.miss {
  color: var(--el-color-warning);
}
/* 行内操作按钮的固定槽位：无论是否显示按钮，行都对齐 */
.row-action {
  display: inline-flex;
  justify-content: flex-end;
  align-items: center;
  min-width: 5em;
  flex-shrink: 0;
}
.field-hint {
  margin-top: 0.4vh;
  font-size: 0.75vmax;
  line-height: 1.5;
  color: var(--app-text-color-placeholder);
}
.type-check {
  position: absolute;
  top: 0.6vh;
  right: 0.4vw;
  font-size: 1vmax;
  color: var(--app-color-primary);
}

/* 已选页面：可编辑 URL 与频率 */
.source-list {
  display: flex;
  flex-direction: column;
  gap: 0.8vh;
}
.source-row {
  display: flex;
  align-items: center;
  gap: 0.8vw;
  padding: 0.6vh 0.8vw;
  background: var(--app-color-blue-light-5);
  border-radius: 0.8vmax;
}
.source-name {
  width: 6vw;
  flex-shrink: 0;
  font-size: 0.88vmax;
  color: var(--app-text-color-regular);
}
.source-url {
  flex: 1;
  min-width: 0;
}
.source-interval {
  width: 7vw;
  flex-shrink: 0;
}
.source-empty {
  display: flex;
  align-items: center;
  gap: 0.5vw;
  padding: 1vh 0.8vw;
  font-size: 0.85vmax;
  color: var(--app-text-color-placeholder);
  background: var(--app-color-orange-light-5);
  border-radius: 0.8vmax;
}

/* 底部 */
.dialog-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1vw;
}
.footer-tip {
  font-size: 0.82vmax;
  color: var(--app-text-color-secondary);
}
.footer-tip b {
  color: var(--app-color-primary);
  font-size: 0.95vmax;
}
.footer-actions {
  display: flex;
  align-items: center;
}
.spin {
  animation: url-check-spin 1s linear infinite;
}
@keyframes url-check-spin {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}
</style>
