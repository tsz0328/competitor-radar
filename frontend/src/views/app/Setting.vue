<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from "vue";
import { useRoute } from "vue-router";
import { storeToRefs } from "pinia";
import { ElMessage, ElMessageBox } from "element-plus";
import {
  ArrowDown,
  Check,
  CircleCheckFilled,
  Connection,
  CopyDocument,
  Cpu,
  Delete,
  Edit,
  Hide,
  InfoFilled,
  Plus,
  Rank,
  Refresh,
  Search,
  Setting as SettingIcon,
  User as UserIcon,
  View,
  Message,
} from "@element-plus/icons-vue";
import {
  activateLlmProvider,
  createLlmProvider,
  deleteLlmProvider,
  duplicateLlmProvider,
  fetchLlmProviders,
  fetchLlmProviderApiKey,
  fetchLlmProviderModels,
  fetchLlmSetting,
  fetchProviderModels,
  testLlmSetting,
  updateLlmProvider,
  updateLlmSetting,
  reorderLlmProviders,
  type LlmProvider,
  type LlmSetting,
  type LlmTestResult,
} from "@/api/setting";
import { fetchSourceTypes } from "@/api/competitor";
import { changeMyPassword, fetchMyProfile, updateMyProfile } from "@/api/user";
import { getSystemSettings, updateSystemSettings } from "@/api/admin";
import UserAvatar from "@/components/UserAvatar.vue";
import { useAuthStore } from "@/stores/auth";
import { fileToSquareDataUrl } from "@/utils/image";
// 服务商图标：本地静态资源，不再运行时请求官网
import iconArk from "@/assets/providers/ark.png";
import iconBailian from "@/assets/providers/bailian.ico";
import iconDeepseek from "@/assets/providers/deepseek.ico";
import iconKimi from "@/assets/providers/kimi.ico";
import iconLongcat from "@/assets/providers/longcat.svg";
import iconMimo from "@/assets/providers/mimo.png";
import iconMinimax from "@/assets/providers/minimax.ico";
import iconModelscope from "@/assets/providers/modelscope.ico";
import iconQianfan from "@/assets/providers/qianfan.ico";
import iconStepfun from "@/assets/providers/stepfun.svg";
import iconZhipu from "@/assets/providers/zhipu.png";
import type { SourceType, SourceTypeOption } from "@/types/competitor";
import { useLlmStore } from "@/stores/llm";
import { usePreferencesStore } from "@/stores/preferences";
import { VueDraggable } from "vue-draggable-plus";

const llmStore = useLlmStore();
// 注意：account 区块在下方才声明 authStore，但左上方分类计算属性（categories）
// 在 setup 早期就会被 applyTabFromQuery 触发，因此这里先初始化 authStore 避免 TDZ。
const authStore = useAuthStore();

/** 设置分类：左侧导航，右侧渲染对应分类内容，便于后续扩展更多分类 */
const baseCategories = [
  { key: "ai", label: "AI 模型", desc: "模型接入与连通性", icon: Cpu },
  {
    key: "preferences",
    label: "添加竞品偏好",
    desc: "官网校验与默认勾选",
    icon: SettingIcon,
  },
  {
    key: "account",
    label: "用户中心",
    desc: "昵称、头像、账号与通知邮箱",
    icon: UserIcon,
  },
];
type CategoryKey = "ai" | "preferences" | "account" | "system";
// 管理员额外看到「系统设置」（发件邮箱等全局配置）
const categories = computed(() => {
  const list = [...baseCategories];
  if (authStore.user?.is_admin) {
    list.push({
      key: "system",
      label: "系统设置",
      desc: "发件邮箱等全局配置",
      icon: Message,
    });
  }
  return list;
});
const activeCategory = ref<string>("ai");

// 支持从侧边栏「用户中心」直接跳过来（/app/setting?tab=account）
const route = useRoute();
function applyTabFromQuery(tab: unknown) {
  const keys = categories.value.map((c) => c.key);
  if (typeof tab === "string" && (keys as string[]).includes(tab)) {
    activeCategory.value = tab as CategoryKey;
  }
}
applyTabFromQuery(route.query.tab);
watch(() => route.query.tab, applyTabFromQuery);

// 添加竞品偏好：存在账号下（服务端），与 CompetitorFormDialog 共用同一个 store
const preferences = usePreferencesStore();
const {
  allowUnreachableOfficial,
  defaultSourceTypes: defaultSelectedTypes,
} = storeToRefs(preferences);
// 偏好加载完成前不回写，否则初始值会把服务端已存的值覆盖掉
const prefsReady = ref(false);
watch(allowUnreachableOfficial, async (v) => {
  if (!prefsReady.value) return;
  await preferences.save({ allowUnreachableOfficial: v });
  ElMessage.success(
    v ? "已开启：官网不可达也可先创建" : "已关闭：官网不可达将拦截保存",
  );
});

// 推荐优先勾选的页面（对竞品监控价值更高）
const RECOMMENDED_TYPES = new Set<SourceType>(["pricing", "changelog"]);
const typeOptions = ref<SourceTypeOption[]>([]);
watch(
  defaultSelectedTypes,
  async (v) => {
    if (!prefsReady.value) return;
    await preferences.save({ defaultSourceTypes: [...v] });
    ElMessage.success("默认勾选已保存");
  },
  { deep: true },
);
async function loadTypes() {
  try {
    typeOptions.value = await fetchSourceTypes();
  } catch {
    // 错误提示由 request.ts 统一弹出
  }
}

/** 恢复默认偏好：官网不放行 + 默认只勾官网首页 */
function resetPreferences() {
  allowUnreachableOfficial.value = false;
  defaultSelectedTypes.value = ["homepage"];
  ElMessage.success("已恢复默认偏好");
}

/** 常见服务商预设：点「从预设模板中选择」展开胶囊列表，点一下自动填好名称与地址。
 *  已按名称首字母（中文按拼音）排序；图标为本地静态资源。 */
const PROVIDER_PRESETS = [
  { key: "qianfan", label: "百度千帆 Coding Plan", baseUrl: "https://qianfan.baidubce.com/v2", model: "qianfan-code-latest", icon: iconQianfan },
  { key: "bailian", label: "Bailian (Qwen)", baseUrl: "https://dashscope.aliyuncs.com/compatible-mode/v1", model: "qwen3-coder-plus", icon: iconBailian },
  { key: "deepseek", label: "DeepSeek", baseUrl: "https://api.deepseek.com/v1", model: "deepseek-v4-flash", icon: iconDeepseek },
  { key: "ark", label: "火山引擎 Ark", baseUrl: "https://ark.cn-beijing.volces.com/api/v3", model: "ark-code-latest", icon: iconArk },
  { key: "kimi", label: "Kimi", baseUrl: "https://api.moonshot.cn/v1", model: "kimi-k2.6", icon: iconKimi },
  { key: "longcat", label: "LongCat", baseUrl: "https://api.longcat.chat/openai/v1", model: "LongCat-Flash-Chat", icon: iconLongcat },
  { key: "minimax", label: "MiniMax (China)", baseUrl: "https://api.minimaxi.com/v1", model: "MiniMax-M3", icon: iconMinimax },
  { key: "modelscope", label: "ModelScope", baseUrl: "https://api-inference.modelscope.cn/v1", model: "ZhipuAI/GLM-5.1", icon: iconModelscope },
  { key: "stepfun", label: "StepFun", baseUrl: "https://api.stepfun.com/v1", model: "step-3.5-flash-2603", icon: iconStepfun },
  { key: "mimo", label: "小米 MiMo", baseUrl: "https://api.xiaomimimo.com/v1", model: "mimo-v2.5-pro", icon: iconMimo },
  { key: "glm", label: "Zhipu GLM", baseUrl: "https://open.bigmodel.cn/api/paas/v4", model: "glm-5.1", icon: iconZhipu },
];

// ---- 全局设置（启用开关；超时等参数无界面，仅透传保存） ----
const form = reactive({
  enabled: false,
  timeoutSeconds: 30,
  minChangeLines: 3,
});

const source = ref<"database" | "env">("env");
const mode = ref<"real" | "mock">("mock");
const statusMessage = ref("");

const loading = ref(false);
const saving = ref(false);

// ---- 已配置供应商列表 ----
const providers = ref<LlmProvider[]>([]);
const actingId = ref<number | null>(null); // 正在切换/删除/复制的供应商
const testingId = ref<number | null>(null); // 正在测试连接的供应商
const isDragging = ref(false); // 拖拽排序进行中：此时忽略行点击，避免误切换

// ---- 添加 / 编辑供应商弹窗 ----
const dialogVisible = ref(false);
const editingId = ref<number | null>(null);
const dialogSaving = ref(false);
const dialogTesting = ref(false);
const dialogTestResult = ref<LlmTestResult | null>(null);
const dlg = reactive({ name: "", baseUrl: "", model: "", apiKey: "" });
// 从上游拉取的模型列表（下拉可搜索选择）
const modelOptions = ref<string[]>([]);
const fetchingModels = ref(false);

/** 本次弹窗内是否改动过模型列表（拉取/手输/删除，决定保存时是否提交给后端） */
const modelsDirty = ref(false);
/** el-select 实例：失焦时用它读回输入框里手打的模型名 */
const modelSelectRef = ref<{ $el?: HTMLElement } | null>(null);

/** 记录一个模型名到候选列表（已存在则忽略） */
function addModelOption(model: string) {
  const name = model.trim();
  if (!name || modelOptions.value.includes(name)) return;
  modelOptions.value = [...modelOptions.value, name];
  modelsDirty.value = true;
}

/** 从候选列表移除一个模型名（列表项右侧的删除图标） */
function removeModelOption(model: string) {
  modelOptions.value = modelOptions.value.filter((m) => m !== model);
  modelsDirty.value = true;
  // 删掉的正好是当前选中的模型：一并清空，避免「有值但不在列表里」的悬空状态
  if (dlg.model === model) {
    dlg.model = "";
    dialogSnapshot.model = "";
  }
}

/**
 * 失焦时把「手打进去、但没按回车确认」的模型名落下来。
 * el-select 的 allow-create 只在回车/点「创建」项时生效，失焦会把输入清空，
 * 这里在它清空前从输入框读回文本，并加入候选列表（自己输入的模型也会被保存）。
 *
 * 但「输入关键词筛选」和「手输新模型」在同一个输入框里，需要区分：
 * - 命中已有项：直接选中它；
 * - 能匹配到已有项（像是筛选词）：不动，避免把关键词误存成模型；
 * - 什么都匹配不到：当作新模型收录（若要强制使用，回车即可）。
 */
function commitTypedModel() {
  const input = modelSelectRef.value?.$el?.querySelector("input");
  const typed = (input?.value ?? "").trim();
  if (!typed) return;
  const lower = typed.toLowerCase();
  const exact = modelOptions.value.find((m) => m.toLowerCase() === lower);
  if (exact) {
    dlg.model = exact;
    dialogSnapshot.model = exact;
    return;
  }
  if (modelOptions.value.some((m) => m.toLowerCase().includes(lower))) return;
  if (typed !== dlg.model) {
    dlg.model = typed;
    dialogSnapshot.model = typed;
  }
  addModelOption(typed);
}

function normalizeUrl(baseUrl: string) {
  return baseUrl.trim().replace(/\/+$/, "").toLowerCase();
}

/** 供应商地址必须是 http(s) 绝对地址（与后端校验一致，提前拦掉明显错的输入） */
function isValidBaseUrl(url: string) {
  return /^https?:\/\/\S+$/i.test(url.trim());
}

/**
 * 模型列表按地址缓存在内存里。
 * 列表接口只回数量，完整列表是按需拉取的；这份缓存用于「切换预设 / 手动改地址」时
 * 立刻带上该地址已知的列表，避免每次都要再请求一次上游。刷新页面即清空。
 */
const modelCacheByUrl = new Map<string, string[]>();

function cacheModelsOf(baseUrl: string, models: string[]) {
  const key = normalizeUrl(baseUrl);
  if (key) modelCacheByUrl.set(key, [...models]);
}

/** 切换预设 / 改地址时，按地址回填已知的模型列表 */
function restoreModelOptions(baseUrl: string) {
  const key = normalizeUrl(baseUrl);
  modelOptions.value = key ? [...(modelCacheByUrl.get(key) ?? [])] : [];
  modelQuery.value = ""; // 清掉上一次的关键词，保证看到完整列表
}

/**
 * 下拉最多渲染多少条：上千个模型全塞进 DOM 会明显卡顿。
 * 超出部分通过输入关键词缩小范围即可看到。
 */
const MAX_RENDERED_MODELS = 300;
const modelQuery = ref("");
/** 真正交给 el-select 渲染的子集：按关键词过滤 + 截断 */
const visibleModelOptions = computed(() => {
  const q = modelQuery.value.trim().toLowerCase();
  const list = q
    ? modelOptions.value.filter((m) => m.toLowerCase().includes(q))
    : modelOptions.value;
  return list.slice(0, MAX_RENDERED_MODELS);
});
/** 空态提示：区分「还没有列表」和「筛选无结果」 */
const modelEmptyText = computed(() =>
  modelOptions.value.length === 0
    ? "还没有模型列表：点「从上游获取」，或直接输入后回车"
    : "没有匹配的模型，回车可直接使用",
);
/**
 * 用自定义过滤接管 el-select 的筛选：
 * 这样「渲染哪些选项」由我们决定（见 visibleModelOptions），只渲染匹配的前 N 条。
 */
function onModelFilter(query: string) {
  modelQuery.value = query;
}

// 编辑时已存 Key 的脱敏预览（明文在打开编辑时单独按 id 拉取回填）
const dialogHasKey = ref(false);
const dialogKeyPreview = ref("");
const dialogKeyLoading = ref(false);
/** 用户点了「清除 Key」：保存时显式清掉已存 Key */
const dialogClearKey = ref(false);

/** 清除已保存的 Key（保存时才真正提交 clearApiKey） */
function clearApiKey() {
  dlg.apiKey = "";
  dialogClearKey.value = true;
}
/** 自定义值快照：切走预设再切回自定义时用于还原 */
const dialogSnapshot = reactive({ baseUrl: "", model: "" });
/** 打开弹窗时的基线快照：用于判断「有没有未保存的修改」 */
const dialogBaseline = reactive({
  name: "",
  baseUrl: "",
  model: "",
  apiKey: "",
  models: "",
});

function modelsSignature(list: string[]) {
  return list.join("\n");
}

/** 弹窗内是否有未保存的修改 */
const dialogDirty = computed(() => {
  if (!dialogVisible.value) return false;
  return (
    dlg.name.trim() !== dialogBaseline.name ||
    dlg.baseUrl.trim() !== dialogBaseline.baseUrl ||
    dlg.model.trim() !== dialogBaseline.model ||
    dlg.apiKey.trim() !== dialogBaseline.apiKey ||
    modelsSignature(modelOptions.value) !== dialogBaseline.models
  );
});

/** 「从预设模板中选择」展开状态 */
const presetOpen = ref(false);
const presetSearch = ref("");
/** 预设按关键词过滤（匹配名称 / 模型 / 地址，不区分大小写） */
const filteredPresets = computed(() => {
  const kw = presetSearch.value.trim().toLowerCase();
  if (!kw) return PROVIDER_PRESETS;
  return PROVIDER_PRESETS.filter(
    (p) =>
      p.label.toLowerCase().includes(kw) ||
      p.model.toLowerCase().includes(kw) ||
      p.baseUrl.toLowerCase().includes(kw),
  );
});
watch(presetOpen, (open) => {
  if (open) presetSearch.value = ""; // 每次展开清空搜索
});

/** 命中的预设（按地址匹配），用于高亮；不匹配任何已知预设即视为自定义 */
const dialogPreset = computed(() => {
  const url = dlg.baseUrl.trim().replace(/\/+$/, "");
  const matched = PROVIDER_PRESETS.find(
    (p) => p.baseUrl && p.baseUrl.replace(/\/+$/, "") === url,
  );
  return matched ? matched.key : "custom";
});

const dialogKeyPlaceholder = computed(() => {
  if (dialogKeyLoading.value) return "正在读取已保存的 Key…";
  if (dialogClearKey.value) return "已标记清除，保存后移除该 Key";
  if (dialogHasKey.value) {
    return `留空表示不修改已保存的 Key（${dialogKeyPreview.value}）`;
  }
  return "请输入 API Key";
});

// ---- API Key 输入框：避开浏览器密码管理器的自动填充 ----
// 用 type=text + CSS 文本遮罩代替 type=password，浏览器不会把它识别成密码框；
// 不支持 -webkit-text-security 的浏览器（如 Firefox）退回 type=password 切换。
/** 明文是否可见 */
const apiKeyVisible = ref(false);
const canCssMask =
  typeof CSS !== "undefined" &&
  typeof CSS.supports === "function" &&
  CSS.supports("-webkit-text-security", "disc");
const apiKeyInputType = computed(() =>
  !apiKeyVisible.value && !canCssMask ? "password" : "text",
);
const apiKeyMasked = computed(() => canCssMask && !apiKeyVisible.value);

/** 反自动填充：默认 readonly（密码管理器会跳过只读框），聚焦后再解除 */
function onApiKeyFocus(e: FocusEvent) {
  (e.target as HTMLInputElement | null)?.removeAttribute("readonly");
}

function applyData(data: LlmSetting) {
  form.enabled = data.enabled;
  form.timeoutSeconds = data.timeoutSeconds;
  form.minChangeLines = data.minChangeLines;
  source.value = data.source;
  mode.value = data.mode;
  statusMessage.value = data.message;
}

async function load() {
  loading.value = true;
  try {
    const [setting, list] = await Promise.all([
      fetchLlmSetting(),
      fetchLlmProviders(),
    ]);
    applyData(setting);
    providers.value = list;
  } catch {
    // 错误提示由 request.ts 统一弹出
  } finally {
    loading.value = false;
  }
}

/** 供应商列表与状态条联动刷新（增删改/切换后调用） */
async function refreshAfterChange() {
  const [setting, list] = await Promise.all([
    fetchLlmSetting(),
    fetchLlmProviders(),
  ]);
  applyData(setting);
  providers.value = list;
  llmStore.refresh();
}

/** 全局启用开关：切换即保存（后端会校验供应商是否配置完整） */
async function saveEnabled() {
  if (
    form.enabled &&
    !providers.value.some((p) => p.isActive && p.hasApiKey)
  ) {
    form.enabled = false;
    ElMessage.warning("启用 AI 前，请先添加一个完整的供应商（地址、模型与 API Key）");
    return;
  }
  saving.value = true;
  try {
    applyData(
      await updateLlmSetting({
        enabled: form.enabled,
        timeoutSeconds: form.timeoutSeconds,
        minChangeLines: form.minChangeLines,
      }),
    );
    ElMessage.success(form.enabled ? "已启用 AI 分析" : "已关闭 AI 分析");
    llmStore.refresh();
  } catch {
    // 失败时把开关弹回去，保持与后端一致
    form.enabled = !form.enabled;
  } finally {
    saving.value = false;
  }
}

// ---- 弹窗：添加 / 编辑 ----

function openCreate() {
  editingId.value = null;
  dlg.name = "";
  dlg.baseUrl = "";
  dlg.model = "";
  dlg.apiKey = "";
  dialogHasKey.value = false;
  dialogKeyPreview.value = "";
  dialogKeyLoading.value = false;
  apiKeyVisible.value = false;
  dialogSnapshot.baseUrl = "";
  dialogSnapshot.model = "";
  modelOptions.value = [];
  modelQuery.value = "";
  modelsDirty.value = false;
  dialogClearKey.value = false;
  // 新建：基线全空（填了任何内容就算「有修改」）
  dialogBaseline.name = "";
  dialogBaseline.baseUrl = "";
  dialogBaseline.model = "";
  dialogBaseline.apiKey = "";
  dialogBaseline.models = "";
  dialogTestResult.value = null;
  dialogVisible.value = true;
}

function openEdit(p: LlmProvider) {
  editingId.value = p.id;
  dlg.name = p.name;
  dlg.baseUrl = p.baseUrl;
  dlg.model = p.model;
  dlg.apiKey = "";
  dialogHasKey.value = p.hasApiKey;
  dialogKeyPreview.value = p.apiKeyPreview;
  apiKeyVisible.value = false;
  dialogSnapshot.baseUrl = p.baseUrl;
  dialogSnapshot.model = p.model;
  // 模型列表先置空，随后按 id 按需拉取（列表接口只回数量）
  modelOptions.value = [];
  modelQuery.value = "";
  modelsDirty.value = false;
  dialogClearKey.value = false;
  // 编辑：以当前值作为基线，未改动时「保存修改」保持灰色
  dialogBaseline.name = p.name;
  dialogBaseline.baseUrl = p.baseUrl;
  dialogBaseline.model = p.model;
  dialogBaseline.apiKey = "";
  dialogBaseline.models = "";
  dialogTestResult.value = null;
  dialogVisible.value = true;
  // 回填已保存的 API Key 明文，方便直接查看 / 修改
  dialogKeyLoading.value = p.hasApiKey;
  if (p.hasApiKey) {
    fetchLlmProviderApiKey(p.id)
      .then((key) => {
        // 期间用户可能已切到别的供应商，避免串值
        if (editingId.value !== p.id) return;
        dlg.apiKey = key;
        dialogBaseline.apiKey = key; // 回填不算「用户修改」
      })
      .catch(() => {
        // 拉取失败则退回占位提示（留空 = 不修改）
      })
      .finally(() => {
        dialogKeyLoading.value = false;
      });
  }
  // 回填已缓存的完整模型列表（同时进内存缓存，切换预设/改地址时可复用）
  if (p.modelsCount > 0) {
    fetchLlmProviderModels(p.id)
      .then((list) => {
        if (editingId.value !== p.id) return;
        modelOptions.value = [...list];
        cacheModelsOf(p.baseUrl, list);
        dialogBaseline.models = modelsSignature(modelOptions.value); // 回填不算「用户修改」
      })
      .catch(() => {
        // 拉取失败则列表为空，仍可点「从上游获取」或手动输入
      });
  }
}

/**
 * 选中 / 回车确认一个模型名：记录快照，并确保它进入候选列表。
 * （回车走的是 allow-create 的创建项，不会经过失焦提交，这里补齐）
 */
function onModelChange() {
  dialogSnapshot.model = dlg.model;
  if (dlg.model.trim()) addModelOption(dlg.model);
}

/** 手动改地址时：记录快照，回填新地址的模型列表，并按新地址覆盖旧的模型列表 */
function onBaseUrlInput() {
  dialogSnapshot.baseUrl = dlg.baseUrl;
  restoreModelOptions(dlg.baseUrl);
  // 地址变了，旧地址拉到的模型列表不再适用：保存时用新地址的列表覆盖
  modelsDirty.value = true;
}

/** 关闭弹窗（点叉 / ESC）前：有未保存修改就先确认 */
async function handleDialogClose(done: () => void) {
  if (!dialogDirty.value) {
    done();
    return;
  }
  try {
    await ElMessageBox.confirm("有未保存的修改，确定放弃并关闭吗？", "未保存的修改", {
      type: "warning",
      confirmButtonText: "继续编辑",
      cancelButtonText: "放弃修改",
      // 区分「点取消」和「点右上角关闭」，避免误把关弹窗当成放弃
      distinguishCancelAndClose: true,
    });
    // 确认 = 继续编辑：留在弹窗里，什么都不做
  } catch (action) {
    // 取消 = 放弃修改 → 关闭；关闭(X) = 继续编辑 → 留在弹窗
    if (action === "cancel") done();
  }
}

/** 关闭弹窗后立即清掉内存里的明文 Key，不在浏览器里残留 */
function onDialogClosed() {
  dlg.apiKey = "";
  dialogKeyPreview.value = "";
  dialogHasKey.value = false;
  dialogKeyLoading.value = false;
  apiKeyVisible.value = false;
  dialogClearKey.value = false;
  modelQuery.value = "";
  modelsDirty.value = false;
}

function applyPreset(preset: (typeof PROVIDER_PRESETS)[number]) {
  // 只预填名称与 API 地址；模型名保持空白，由「从上游获取」或手动填写
  dlg.baseUrl = preset.baseUrl;
  dlg.model = "";
  if (!editingId.value) dlg.name = preset.label;
  dialogSnapshot.baseUrl = dlg.baseUrl;
  dialogSnapshot.model = dlg.model;
  restoreModelOptions(preset.baseUrl); // 该地址若拉过模型，直接带上
  modelsDirty.value = true; // 地址变了：模型列表按新地址覆盖
  presetOpen.value = false;
}

/** 拉取模型列表的等待时间：/models 有时比 chat 慢，单独放宽（与设置里的对话超时无关） */
const MODEL_FETCH_TIMEOUT_S = 60;

/** 从上游供应商拉取模型列表，填充模型名称下拉（OpenAI 兼容 GET /models）。 */
async function fetchModels() {
  if (!isValidBaseUrl(dlg.baseUrl)) {
    ElMessage.warning("请先填写正确的 API 地址（http/https）");
    return;
  }
  if (!editingId.value && !dlg.apiKey.trim()) {
    ElMessage.warning("请先填写 API Key");
    return;
  }
  fetchingModels.value = true;
  try {
    const res = await fetchProviderModels({
      providerId: editingId.value ?? undefined,
      baseUrl: dlg.baseUrl.trim() || undefined,
      apiKey: dlg.apiKey.trim() || undefined,
      timeoutSeconds: MODEL_FETCH_TIMEOUT_S,
    });
    if (res.ok && res.models.length) {
      // 把获取到的模型「追加」进列表：已有的不重复添加，已手输的也保留
      const merged = [...modelOptions.value];
      for (const m of res.models) {
        if (!merged.includes(m)) merged.push(m);
      }
      modelOptions.value = merged;
      modelsDirty.value = true;
      // 记住这次结果（切换预设/改地址可复用）；是否落库由「保存」决定
      cacheModelsOf(dlg.baseUrl, merged);
      ElMessage.success(`已获取 ${res.models.length} 个模型`);
      // 当前模型不在列表里也保留（allow-create 允许手填），仅提示
      if (dlg.model && !res.models.includes(dlg.model)) {
        ElMessage.info(`当前模型「${dlg.model}」不在列表内，可继续手动选用`);
      }
    } else {
      ElMessage.warning(res.message || "未获取到模型列表");
    }
  } catch {
    // 错误提示由 request.ts 统一弹出
  } finally {
    fetchingModels.value = false;
  }
}

async function testDialog() {
  if (!isValidBaseUrl(dlg.baseUrl)) {
    ElMessage.warning("请填写正确的 API 地址（以 http:// 或 https:// 开头）");
    return;
  }
  if (!dlg.model.trim()) {
    ElMessage.warning("请先填写模型名称");
    return;
  }
  if (!editingId.value && !dlg.apiKey.trim()) {
    ElMessage.warning("请先填写 API Key");
    return;
  }
  dialogTesting.value = true;
  dialogTestResult.value = null;
  try {
    dialogTestResult.value = await testLlmSetting({
      providerId: editingId.value ?? undefined,
      baseUrl: dlg.baseUrl.trim() || undefined,
      model: dlg.model.trim() || undefined,
      // 编辑时留空 = 用已保存的 Key 测试（由后端取）
      apiKey: dlg.apiKey.trim() || undefined,
      timeoutSeconds: form.timeoutSeconds,
    });
  } catch {
    // 错误提示由 request.ts 统一弹出
  } finally {
    dialogTesting.value = false;
  }
}

async function saveDialog() {
  if (!isValidBaseUrl(dlg.baseUrl)) {
    ElMessage.warning("请填写正确的 API 地址（以 http:// 或 https:// 开头）");
    return;
  }
  if (!dlg.model.trim()) {
    ElMessage.warning("请先填写模型名称");
    return;
  }
  if (!editingId.value && !dlg.apiKey.trim()) {
    ElMessage.warning("请先填写 API Key");
    return;
  }
  dialogSaving.value = true;
  try {
    if (editingId.value) {
      await updateLlmProvider(editingId.value, {
        name: dlg.name.trim(),
        baseUrl: dlg.baseUrl.trim(),
        model: dlg.model.trim(),
        // 点过「清除 Key」→ 显式清掉；否则留空表示保留已存的 Key
        clearApiKey: dialogClearKey.value,
        apiKey: dialogClearKey.value ? undefined : dlg.apiKey.trim() || undefined,
        // 本次改过列表才提交，避免把已有列表清空
        models: modelsDirty.value ? [...modelOptions.value] : undefined,
      });
      ElMessage.success("供应商已更新");
    } else {
      await createLlmProvider({
        name: dlg.name.trim() || undefined,
        baseUrl: dlg.baseUrl.trim(),
        model: dlg.model.trim(),
        apiKey: dlg.apiKey.trim(),
        models: modelsDirty.value ? [...modelOptions.value] : undefined,
      });
      ElMessage.success("供应商已添加");
    }
    dialogVisible.value = false;
    await refreshAfterChange();
  } catch {
    // 错误提示由 request.ts 统一弹出
  } finally {
    dialogSaving.value = false;
  }
}

async function activate(p: LlmProvider) {
  if (p.isActive) return; // 已经是使用中的，无需重复切换
  // 拖拽排序中 / 已有请求在跑：忽略点击，避免误切换与连点重复请求
  if (isDragging.value || actingId.value !== null) return;
  actingId.value = p.id;
  try {
    await activateLlmProvider(p.id);
    ElMessage.success(`已切换到「${p.name || "自定义"}」`);
    await refreshAfterChange();
  } catch {
    // 错误提示由 request.ts 统一弹出
  } finally {
    actingId.value = null;
  }
}

// ---- 拖动排序（SortableJS：拖动过程中实时重排 + FLIP 动画） ----
/** 拖动结束后 VueDraggable 回传新数组：同步本地顺序并落库 */
function onReorder(list: LlmProvider[]) {
  providers.value = list;
  persistOrder();
}
async function persistOrder() {
  try {
    await reorderLlmProviders(providers.value.map((p) => p.id));
  } catch {
    load(); // 失败回滚：重新拉取正确顺序
  }
}

/** 测试某条已保存供应商的连通性（Key 由后端取，前端拿不到明文） */
async function testProvider(p: LlmProvider) {
  testingId.value = p.id;
  try {
    const res = await testLlmSetting({
      providerId: p.id,
      timeoutSeconds: form.timeoutSeconds,
    });
    if (res.ok) ElMessage.success(res.message);
    else ElMessage.error(res.message);
  } catch {
    // 错误提示由 request.ts 统一弹出
  } finally {
    testingId.value = null;
  }
}

/** 复制供应商（含已保存的 Key），副本追加到末尾 */
async function duplicate(p: LlmProvider) {
  actingId.value = p.id;
  try {
    await duplicateLlmProvider(p.id);
    ElMessage.success("已复制供应商");
    await refreshAfterChange();
  } catch {
    // 错误提示由 request.ts 统一弹出
  } finally {
    actingId.value = null;
  }
}

async function remove(p: LlmProvider) {
  try {
    await ElMessageBox.confirm(
      `确定删除「${p.name || "自定义"}」吗？${
        p.isActive ? "它是当前使用中的供应商，删除后会自动切换到其它供应商。" : ""
      }`,
      "删除供应商",
      { type: "warning", confirmButtonText: "删除", cancelButtonText: "取消" },
    );
  } catch {
    return; // 用户取消
  }
  actingId.value = p.id;
  try {
    await deleteLlmProvider(p.id);
    ElMessage.success("已删除");
    await refreshAfterChange();
  } catch {
    // 错误提示由 request.ts 统一弹出
  } finally {
    actingId.value = null;
  }
}

// ---- 用户中心：账号资料 / 头像 / 通知邮箱 / 修改密码 ----

const account = reactive({
  // 昵称：初始化默认取账号（服务端没单独设过昵称时）
  nickname: "",
  username: "",
  email: "",
  avatar: "",
  passwordLength: null as number | null,
});
const accountSaving = ref(false);
const editingProfile = ref(false); // 是否展开「修改资料」编辑框
const avatarUploading = ref(false);
const avatarInputRef = ref<HTMLInputElement | null>(null);
const pwd = reactive({ oldPassword: "", newPassword: "", confirmPassword: "" });

/** 原密码框默认 readonly（阻止浏览器自动预填）；用户点一下聚焦即解除只读 */
function unlockOldPassword(e: FocusEvent) {
  const el = e.target as HTMLInputElement | null;
  el?.removeAttribute("readonly");
}

/** 头像预览：与顶栏/侧栏共用同一套首字母与配色算法（用账号作为展示名） */
const accountPreviewUser = computed(() => ({
  id: authStore.user?.id ?? 0,
  name: account.username || authStore.user?.name || "",
  avatar: account.avatar,
}));

async function loadAccount() {
  try {
    const profile = await fetchMyProfile();
    // 昵称初始化默认是账号：没单独设过昵称就用账号填上，不留空
    account.nickname = profile.nickname || profile.username;
    account.username = profile.username;
    account.email = profile.email;
    account.avatar = profile.avatar;
    account.passwordLength = profile.passwordLength;
  } catch {
    // 错误提示由 request.ts 统一弹出
  }
}

function pickAvatar() {
  avatarInputRef.value?.click();
}

/** 选图后在前端居中裁剪 + 压缩成 data URL（见 utils/image.ts），并即时同步服务端 */
async function onAvatarPicked(event: Event) {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  input.value = ""; // 允许重复选择同一个文件
  if (!file) return;
  avatarUploading.value = true;
  try {
    account.avatar = await fileToSquareDataUrl(file);
    await persistAvatar();
  } catch (e) {
    ElMessage.error((e as Error).message || "头像处理失败");
  } finally {
    avatarUploading.value = false;
  }
}

/** 头像变更即时保存到服务端，并同步 auth store（侧栏/顶栏头像立刻跟着变） */
async function persistAvatar() {
  try {
    const profile = await updateMyProfile({ avatar: account.avatar });
    account.nickname = profile.nickname || profile.username;
    account.username = profile.username;
    account.email = profile.email;
    account.avatar = profile.avatar;
    authStore.setUser({
      id: profile.id,
      name: profile.nickname || profile.username,
      username: profile.username,
      avatar: profile.avatar,
      email: profile.email,
      is_admin: profile.is_admin,
    });
    ElMessage.success("头像已更新");
  } catch {
    // 错误提示由 request.ts 统一弹出
  }
}

/** 保存账号资料 +（可选）修改密码：成功后同步 auth store，侧边栏与只读展示立刻刷新 */
async function saveAccount() {
  if (!account.username.trim()) {
    ElMessage.warning("账号不能为空");
    return;
  }
  // 三个密码框只要填了任意一个，就视为本次要改密码
  const changingPassword = Boolean(
    pwd.oldPassword || pwd.newPassword || pwd.confirmPassword,
  );
  if (changingPassword) {
    if (!pwd.oldPassword) {
      ElMessage.warning("请输入原密码");
      return;
    }
    if (pwd.newPassword.length < 6) {
      ElMessage.warning("新密码至少 6 位");
      return;
    }
    if (pwd.newPassword !== pwd.confirmPassword) {
      ElMessage.warning("两次输入的新密码不一致");
      return;
    }
  }
  accountSaving.value = true;
  try {
    // 先改密码：原密码错误时直接中止，避免资料被单独改动
    if (changingPassword) {
      await changeMyPassword({
        oldPassword: pwd.oldPassword,
        newPassword: pwd.newPassword,
      });
      pwd.oldPassword = "";
      pwd.newPassword = "";
      pwd.confirmPassword = "";
    }
    const profile = await updateMyProfile({
      nickname: account.nickname.trim(),
      username: account.username.trim(),
      email: account.email.trim(),
      avatar: account.avatar,
    });
    account.nickname = profile.nickname || profile.username;
    account.username = profile.username;
    account.email = profile.email;
    account.avatar = profile.avatar;
    account.passwordLength = profile.passwordLength;
    authStore.setUser({
      id: profile.id,
      name: profile.nickname || profile.username,
      username: profile.username,
      avatar: profile.avatar,
      email: profile.email,
      is_admin: profile.is_admin,
    });
    editingProfile.value = false;
    ElMessage.success(changingPassword ? "资料与密码已保存" : "账号资料已保存");
  } catch {
    // 错误提示由 request.ts 统一弹出
  } finally {
    accountSaving.value = false;
  }
}

/** 取消修改：关掉编辑框并把本地值还原成服务端已存的值 */
async function cancelEditProfile() {
  editingProfile.value = false;
  pwd.oldPassword = "";
  pwd.newPassword = "";
  pwd.confirmPassword = "";
  await loadAccount();
}

// ---- 系统设置（仅管理员可见）：发件邮箱 ----
// ---- 系统设置（仅管理员可见）：完整 SMTP 发件配置 ----
const sysForm = reactive({
  smtp_host: "",
  smtp_port: 465 as number | null,
  smtp_username: "",
  smtp_password: "",
  smtp_sender: "",
});
const sysPasswordSet = ref(false);
const sysEditing = ref(false);
const sysSaving = ref(false);
async function loadSystem() {
  const s = await getSystemSettings();
  sysForm.smtp_host = s.smtp_host;
  sysForm.smtp_port = s.smtp_port || 465;
  sysForm.smtp_username = s.smtp_username;
  sysForm.smtp_sender = s.smtp_sender;
  sysPasswordSet.value = s.smtp_password_set;
  // 授权码出于安全不回传，前端始终留空（"留空=不修改"）
  sysForm.smtp_password = "";
}
/** 只读展示用的授权码：已设置就显示打码，否则"未设置" */
const sysPasswordMasked = computed(() =>
  sysPasswordSet.value ? "*".repeat(12) : "未设置",
);
function cancelSystem() {
  sysEditing.value = false;
  sysForm.smtp_password = "";
  loadSystem();
}
async function saveSystem() {
  sysSaving.value = true;
  try {
    const s = await updateSystemSettings({
      smtp_host: sysForm.smtp_host,
      smtp_port: sysForm.smtp_port ?? 465,
      smtp_username: sysForm.smtp_username,
      smtp_sender: sysForm.smtp_sender,
      // 只有用户真填了授权码才传；空串=不改动
      smtp_password: sysForm.smtp_password,
    });
    sysForm.smtp_host = s.smtp_host;
    sysForm.smtp_port = s.smtp_port || 465;
    sysForm.smtp_username = s.smtp_username;
    sysForm.smtp_sender = s.smtp_sender;
    sysPasswordSet.value = s.smtp_password_set;
    sysForm.smtp_password = "";
    sysEditing.value = false;
    ElMessage.success("系统设置已保存");
  } catch {
    // 错误提示由 request.ts 统一弹出
  } finally {
    sysSaving.value = false;
  }
}

onMounted(async () => {
  // 先把账号偏好读回来，再允许回写
  await preferences.ensureLoaded();
  prefsReady.value = true;
  load();
  loadTypes();
  loadAccount();
  if (authStore.user?.is_admin) {
    loadSystem();
  }
});
</script>

<template>
  <div class="setting-page" v-loading="loading">
    <header class="page-header">
      <h1 class="title">设置</h1>
      <p class="subtitle">配置 AI 模型与运行偏好，让竞品雷达按你的方式工作</p>
    </header>

    <div class="setting-body">
      <nav class="category-nav" aria-label="设置分类">
        <button
          v-for="cat in categories"
          :key="cat.key"
          type="button"
          class="category-item"
          :class="{ active: activeCategory === cat.key }"
          @click="activeCategory = cat.key"
        >
          <span class="category-icon"><el-icon><component :is="cat.icon" /></el-icon></span>
          <span class="category-meta">
            <span class="category-label">{{ cat.label }}</span>
            <span class="category-desc">{{ cat.desc }}</span>
          </span>
        </button>
      </nav>

      <div class="category-content">
        <section v-show="activeCategory === 'ai'" class="panel">
          <div class="panel-head">
            <div class="panel-title-wrap">
              <span class="panel-icon"><el-icon><Cpu /></el-icon></span>
              <div>
                <div class="panel-title">AI 模型</div>
                <div class="panel-desc">
                  用于事件分类、趋势判断与周报撰写，兼容任意 OpenAI 接口
                </div>
              </div>
            </div>
            <div class="status-chip" :class="mode">
              <span class="dot" />
              {{ mode === "real" ? "真实模型" : "规则 Mock" }}
            </div>
          </div>

          <div class="status-bar" :class="mode">
            <el-icon class="status-icon">
              <component :is="mode === 'real' ? CircleCheckFilled : InfoFilled" />
            </el-icon>
            <span class="status-message">{{ statusMessage }}</span>
            <el-tag v-if="source === 'env'" size="small" type="info" effect="plain">
              来自 .env
            </el-tag>
            <el-tag v-else size="small" type="success" effect="plain">
              已在设置页保存
            </el-tag>
          </div>

          <div class="switch-row">
            <div class="switch-text">
              <div class="switch-label">启用 AI 分析</div>
              <div class="switch-hint">
                关闭时使用规则引擎兜底，无需 Key 也能跑通全流程
              </div>
            </div>
            <el-switch v-model="form.enabled" :loading="saving" @change="saveEnabled" />
          </div>

          <el-divider />

          <div class="list-head">
            <div>
              <div class="field-label">已配置供应商</div>
              <div class="list-sub">拖动⠿可调整顺序，点击列表行即切换为「使用中」</div>
            </div>
            <el-button type="primary" :icon="Plus" @click="openCreate">
              添加供应商
            </el-button>
          </div>

          <VueDraggable
            :model-value="providers"
            class="provider-list"
            :animation="180"
            handle=".drag-handle"
            draggable=".provider-item"
            ghost-class="drag-ghost"
            chosen-class="drag-chosen"
            :force-fallback="true"
            @start="isDragging = true"
            @end="isDragging = false"
            @update:model-value="onReorder"
          >
            <div
              v-for="p in providers"
              :key="p.id"
              class="provider-item"
              :class="{ active: p.isActive }"
              role="button"
              tabindex="0"
              :aria-label="`切换到「${p.name || '自定义'}」`"
              @click="activate(p)"
              @keydown.enter="activate(p)"
            >
              <button
                type="button"
                class="drag-handle"
                title="按住拖动调整顺序"
                @click.stop
              >
                <el-icon><Rank /></el-icon>
              </button>
              <div class="provider-body">
                <div class="provider-top">
                  <span class="provider-name">{{ p.name || "自定义" }}</span>
                  <el-tag v-if="p.isActive" type="success" size="small" effect="light">
                    使用中
                  </el-tag>
                </div>
                <div class="provider-meta">
                  <span class="meta-label">地址</span>
                  <span class="meta-value meta-url" :title="p.baseUrl">{{ p.baseUrl }}</span>
                  <span class="meta-label">模型</span>
                  <span class="meta-value">{{ p.model }}</span>
                  <span class="meta-label">Key</span>
                  <span class="meta-value">{{ p.hasApiKey ? p.apiKeyPreview : "未配置" }}</span>
                </div>
              </div>

              <div class="provider-actions" @click.stop>
                <el-tooltip content="测试连接" placement="top">
                  <el-button
                    text
                    circle
                    size="large"
                    aria-label="测试连接"
                    :icon="Connection"
                    :loading="testingId === p.id"
                    @click.stop="testProvider(p)"
                  />
                </el-tooltip>
                <el-tooltip content="编辑" placement="top">
                  <el-button
                    text
                    circle
                    size="large"
                    aria-label="编辑"
                    :icon="Edit"
                    @click.stop="openEdit(p)"
                  />
                </el-tooltip>
                <el-tooltip content="复制" placement="top">
                  <el-button
                    text
                    circle
                    size="large"
                    aria-label="复制"
                    :icon="CopyDocument"
                    :disabled="actingId === p.id"
                    @click.stop="duplicate(p)"
                  />
                </el-tooltip>
                <el-tooltip content="删除" placement="top">
                  <el-button
                    text
                    circle
                    size="large"
                    class="action-danger"
                    aria-label="删除"
                    :icon="Delete"
                    :loading="actingId === p.id"
                    @click.stop="remove(p)"
                  />
                </el-tooltip>
              </div>
            </div>

            <el-empty
              v-if="!providers.length"
              description="还没有添加供应商，点击右上角「添加供应商」开始配置"
              :image-size="80"
            />
          </VueDraggable>

          <p class="footnote">
            提示：API Key 仅保存在你的服务器本地数据库，不会写入日志；列表只显示脱敏预览，
            编辑某条供应商时会取回明文以便直接修改。
          </p>
        </section>

        <section v-show="activeCategory === 'preferences'" class="panel">
          <div class="panel-head">
            <div class="panel-title-wrap">
              <span class="panel-icon"><el-icon><SettingIcon /></el-icon></span>
              <div>
                <div class="panel-title">添加竞品偏好</div>
                <div class="panel-desc">控制新增竞品时的网址校验宽松度</div>
              </div>
            </div>
          </div>

          <div class="switch-row">
            <div class="switch-text">
              <div class="switch-label">官网不可达时也允许创建</div>
              <div class="switch-hint">
                默认关闭：官网无法访问时会拦截保存。开启后，官网暂时不可达也能先创建，稍后在详情中修正。
              </div>
            </div>
            <el-switch v-model="allowUnreachableOfficial" />
          </div>

          <el-divider />

          <div class="field-block">
            <div class="field-label">新增竞品时默认勾选的监控页面</div>
            <el-checkbox-group v-model="defaultSelectedTypes">
              <el-checkbox
                v-for="opt in typeOptions"
                :key="opt.type"
                :value="opt.type"
              >
                {{ opt.label }}
                <em v-if="RECOMMENDED_TYPES.has(opt.type)" class="rec-tag">推荐</em>
              </el-checkbox>
            </el-checkbox-group>
            <div class="field-hint">
              仅影响新建弹窗的初始勾选；一个都不选时默认只勾「官网首页」。
            </div>
          </div>

          <div class="actions">
            <el-button @click="resetPreferences">恢复默认</el-button>
          </div>
        </section>

        <section v-show="activeCategory === 'account'" class="panel">
          <div class="panel-head">
            <div class="panel-title-wrap">
              <span class="panel-icon"><el-icon><UserIcon /></el-icon></span>
              <div>
                <div class="panel-title">用户中心</div>
                <div class="panel-desc">昵称、头像、账号与接收通知的邮箱</div>
              </div>
            </div>
          </div>

          <div class="account-avatar-row">
            <span class="avatar-label">头像：</span>
            <UserAvatar :user="accountPreviewUser" :size="64" />
            <el-button :loading="avatarUploading" @click="pickAvatar">
              修改头像
            </el-button>
            <input
              ref="avatarInputRef"
              class="hidden-file"
              type="file"
              accept="image/*"
              @change="onAvatarPicked"
            />
          </div>
          <div class="field-hint avatar-hint">
            支持 jpg / png / webp；会自动居中裁剪并压缩，修改后即时保存，无需点「保存资料」
          </div>

          <!-- 只读展示：默认显示昵称 / 账号 / 密码 / 邮箱，点「修改」才变输入框 -->
          <div v-if="!editingProfile" class="account-info">
            <div class="info-item">
              <span class="info-label">昵称</span>
              <!-- 没单独设过昵称时默认就是账号 -->
              <span class="info-value">{{ account.nickname || "未设置" }}</span>
            </div>
            <div class="info-item">
              <span class="info-label">账号</span>
              <span class="info-value">{{ account.username }}</span>
            </div>
            <div class="info-item">
              <span class="info-label">密码</span>
              <span class="info-value">{{
                account.passwordLength == null ? "未设置" : "*".repeat(12)
              }}</span>
            </div>
            <div class="info-item">
              <span class="info-label">邮箱</span>
              <span class="info-value">{{ account.email || "未设置" }}</span>
            </div>
          </div>
          <div v-if="!editingProfile" class="actions">
            <el-button type="primary" @click="editingProfile = true">修改</el-button>
          </div>

          <!-- 编辑态：昵称 / 账号 / 密码 / 邮箱，统一用底部「保存」提交 -->
          <template v-if="editingProfile">
            <el-form label-position="top" autocomplete="off" @submit.prevent>
              <el-form-item label="昵称">
                <el-input
                  v-model="account.nickname"
                  maxlength="50"
                  clearable
                  placeholder="展示用昵称，默认与账号相同"
                />
              </el-form-item>
              <el-form-item label="账号">
                <el-input
                  v-model="account.username"
                  maxlength="50"
                  clearable
                  placeholder="登录用的账号，全局唯一"
                />
              </el-form-item>
              <el-form-item label="原密码">
                <!-- readonly + off：浏览器不会自动填充保存的密码；用户点一下聚焦即解除只读 -->
                <el-input
                  v-model="pwd.oldPassword"
                  name="account-old-password"
                  type="password"
                  show-password
                  autocomplete="off"
                  readonly
                  @focus="unlockOldPassword"
                  placeholder="不修改密码可留空"
                />
              </el-form-item>
              <el-form-item label="新密码">
                <el-input
                  v-model="pwd.newPassword"
                  name="account-new-password"
                  type="password"
                  show-password
                  autocomplete="new-password"
                  placeholder="不修改密码可留空；至少 6 位"
                />
              </el-form-item>
              <el-form-item label="确认新密码">
                <el-input
                  v-model="pwd.confirmPassword"
                  name="account-confirm-password"
                  type="password"
                  show-password
                  autocomplete="new-password"
                />
              </el-form-item>
              <el-form-item label="接收通知的邮箱">
                <el-input
                  v-model="account.email"
                  maxlength="100"
                  clearable
                  placeholder="留空表示不单独接收，回退运维配置的收件人"
                />
              </el-form-item>
            </el-form>
            <div class="field-hint">
              竞品出现高优先级变化时，即时通知会发到这个邮箱。
            </div>
            <div class="actions">
              <el-button
                type="primary"
                :loading="accountSaving"
                @click="saveAccount"
              >
                保存
              </el-button>
              <el-button :disabled="accountSaving" @click="cancelEditProfile">
                取消
              </el-button>
            </div>
          </template>
        </section>

        <section v-show="activeCategory === 'system'" class="panel">
          <div class="panel-head">
            <div class="panel-title-wrap">
              <span class="panel-icon"><el-icon><Message /></el-icon></span>
              <div>
                <div class="panel-title">系统设置</div>
                <div class="panel-desc">SMTP 发件配置（仅管理员可改）</div>
              </div>
            </div>
          </div>

          <!-- 只读展示：默认显示当前配置，点「修改」才变输入框 -->
          <div v-if="!sysEditing" class="account-info">
            <div class="info-item">
              <span class="info-label">SMTP 服务器</span>
              <span class="info-value">{{ sysForm.smtp_host || "未设置" }}</span>
            </div>
            <div class="info-item">
              <span class="info-label">端口</span>
              <span class="info-value">{{ sysForm.smtp_port || "未设置" }}</span>
            </div>
            <div class="info-item">
              <span class="info-label">用户名</span>
              <span class="info-value">{{ sysForm.smtp_username || "未设置" }}</span>
            </div>
            <div class="info-item">
              <span class="info-label">授权码</span>
              <span class="info-value">{{ sysPasswordMasked }}</span>
            </div>
            <div class="info-item">
              <span class="info-label">发件邮箱</span>
              <span class="info-value">{{ sysForm.smtp_sender || "未设置" }}</span>
            </div>
          </div>
          <div v-if="!sysEditing" class="actions">
            <el-button type="primary" @click="sysEditing = true">修改</el-button>
          </div>

          <!-- 编辑态：完整 SMTP 表单 -->
          <template v-if="sysEditing">
            <el-form label-position="top" autocomplete="off" @submit.prevent>
              <el-form-item label="SMTP 服务器">
                <el-input
                  v-model="sysForm.smtp_host"
                  maxlength="200"
                  clearable
                  placeholder="如 smtp.qq.com；留空则回退 .env 的 SMTP_HOST"
                />
              </el-form-item>
              <el-form-item label="端口">
                <el-input
                  v-model.number="sysForm.smtp_port"
                  type="number"
                  placeholder="465（SSL）；587 多为 STARTTLS"
                />
              </el-form-item>
              <el-form-item label="用户名（登录账号）">
                <el-input
                  v-model="sysForm.smtp_username"
                  name="smtp-username"
                  autocomplete="off"
                  maxlength="200"
                  clearable
                  placeholder="通常是邮箱全名；留空则回退 .env 的 SMTP_USERNAME"
                />
              </el-form-item>
              <el-form-item label="授权码">
                <!-- new-password：明确告诉浏览器这是"新密码"字段，不要预填已保存的站点登录密码 -->
                <el-input
                  v-model="sysForm.smtp_password"
                  name="smtp-authcode"
                  autocomplete="new-password"
                  type="password"
                  show-password
                  maxlength="200"
                  placeholder="留空表示不修改；换账号时填新账号的授权码"
                />
              </el-form-item>
              <el-form-item label="发件邮箱（SMTP From）">
                <el-input
                  v-model="sysForm.smtp_sender"
                  maxlength="100"
                  clearable
                  placeholder="如 no-reply@example.com；留空则回退 .env 的 SMTP_SENDER"
                />
              </el-form-item>
            </el-form>
            <div class="field-hint">
              服务器 / 端口 / 用户名 / 发件邮箱留空表示清掉覆盖、回退 .env；授权码留空表示不修改（出于安全不回传明文）。
              界面配置优先于 .env，保存后立即生效，无需重启。用户名与授权码必须成套，只换其一会导致登录失败、邮件发不出。
            </div>
            <div class="actions">
              <el-button type="primary" :loading="sysSaving" @click="saveSystem">
                保存
              </el-button>
              <el-button :disabled="sysSaving" @click="cancelSystem">取消</el-button>
            </div>
          </template>
        </section>
      </div>
    </div>

    <el-dialog
      v-model="dialogVisible"
      :title="editingId ? '编辑供应商' : '添加供应商'"
      width="680px"
      destroy-on-close
      :close-on-click-modal="false"
      :before-close="handleDialogClose"
      @closed="onDialogClosed"
    >
      <el-form label-position="top" autocomplete="off">
        <el-form-item label="服务商">
          <el-popover
            v-model:visible="presetOpen"
            placement="bottom-start"
            :width="640"
            trigger="click"
            :teleported="false"
          >
            <template #reference>
              <button type="button" class="preset-trigger">
                <span>从预设模板中选择</span>
                <el-icon :class="{ open: presetOpen }"><ArrowDown /></el-icon>
              </button>
            </template>
            <el-input
              v-model="presetSearch"
              class="preset-search"
              placeholder="搜索服务商 / 模型 / 地址"
              clearable
              :prefix-icon="Search"
            />
            <div class="preset-grid">
              <button
                v-for="preset in filteredPresets"
                :key="preset.key"
                type="button"
                class="preset-chip"
                :class="{ active: dialogPreset === preset.key }"
                @click="applyPreset(preset)"
              >
                <span class="preset-avatar">
                  <img :src="preset.icon" :alt="preset.label" />
                </span>
                <span class="preset-name">{{ preset.label }}</span>
                <span class="preset-model">{{ preset.model }}</span>
              </button>
              <div v-if="!filteredPresets.length" class="preset-empty">
                没有匹配的预设，可直接在下方手动填写
              </div>
            </div>
          </el-popover>
        </el-form-item>

        <el-form-item label="名称">
          <el-input
            v-model="dlg.name"
            placeholder="给自己看的备注名，如 DeepSeek 主力"
            maxlength="80"
            clearable
          />
        </el-form-item>

        <el-form-item label="API 地址">
          <el-input
            v-model="dlg.baseUrl"
            placeholder="https://api.deepseek.com/v1"
            clearable
            @input="onBaseUrlInput"
          />
        </el-form-item>

        <el-form-item label="模型名称">
          <div class="model-field">
            <el-select
              ref="modelSelectRef"
              v-model="dlg.model"
              class="model-select"
              filterable
              allow-create
              default-first-option
              placeholder="输入关键词筛选，或点右侧按钮获取"
              :filter-method="onModelFilter"
              :no-data-text="modelEmptyText"
              @change="onModelChange"
              @blur="commitTypedModel"
            >
              <el-option v-for="m in visibleModelOptions" :key="m" :label="m" :value="m">
                <div class="model-option">
                  <span class="model-option-label">{{ m }}</span>
                  <el-icon
                    class="model-option-del"
                    role="button"
                    :aria-label="`从列表移除 ${m}`"
                    title="从列表中移除"
                    @click.stop.prevent="removeModelOption(m)"
                  >
                    <Delete />
                  </el-icon>
                </div>
              </el-option>
            </el-select>
            <el-button :icon="Refresh" :loading="fetchingModels" @click="fetchModels">
              从上游获取
            </el-button>
          </div>
        </el-form-item>

        <el-form-item label="API Key">
          <div class="model-field">
            <el-input
              v-model="dlg.apiKey"
              class="api-key-input"
              name="llm-provider-api-key"
              :type="apiKeyInputType"
              clearable
              autocomplete="new-password"
              :readonly="!canCssMask"
              :disabled="dialogKeyLoading"
              :placeholder="dialogKeyPlaceholder"
              :class="{ 'secret-masked': apiKeyMasked }"
              @focus="onApiKeyFocus"
              @input="dialogClearKey = false"
            >
              <template #suffix>
                <el-icon class="pwd-eye" @click.stop="apiKeyVisible = !apiKeyVisible">
                  <View v-if="apiKeyVisible" />
                  <Hide v-else />
                </el-icon>
              </template>
            </el-input>
            <el-button
              v-if="editingId !== null && (dialogHasKey || dlg.apiKey)"
              text
              :disabled="dialogKeyLoading"
              @click="clearApiKey"
            >
              清除
            </el-button>
          </div>
        </el-form-item>
      </el-form>

      <el-alert
        v-if="dialogTestResult"
        class="test-alert"
        :type="dialogTestResult.ok ? 'success' : 'error'"
        :closable="false"
        show-icon
        :title="dialogTestResult.message"
      />

      <template #footer>
        <el-button :icon="Connection" :loading="dialogTesting" @click="testDialog">
          测试连接
        </el-button>
        <el-button
          type="primary"
          :icon="Check"
          :loading="dialogSaving"
          :disabled="editingId !== null && !dialogDirty"
          @click="saveDialog"
        >
          {{ editingId ? "保存修改" : "添加" }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.setting-page {
  height: 100%;
  padding: 2vh 2vw;
  display: flex;
  flex-direction: column;
  gap: 2vh;
}

.page-header {
  padding: 0 0.2vw;
}
.title {
  margin: 0 0 0.4vh;
  font-size: 1.6vmax;
  font-weight: bold;
}
.subtitle {
  margin: 0;
  font-size: 1vmax;
  color: var(--app-text-color-secondary);
}

.panel {
  width: 100%;
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  background-color: var(--app-color-white);
  border-radius: 1vmax;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.1);
  padding: 1.8vh 1.4vw;
}

.panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1vw;
}
.panel-title-wrap {
  display: flex;
  align-items: center;
  gap: 0.8vw;
}
.panel-icon {
  width: 2.8vmax;
  height: 2.8vmax;
  border-radius: 0.8vmax;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1.5vmax;
  color: var(--app-color-white);
  background: linear-gradient(
    135deg,
    var(--app-color-blue),
    var(--app-color-purple)
  );
}
.panel-title {
  font-size: 1.2vmax;
  font-weight: bold;
}
.panel-desc {
  font-size: 0.9vmax;
  color: var(--app-text-color-secondary);
  margin-top: 0.2vh;
}

.status-chip {
  display: flex;
  align-items: center;
  gap: 0.4vw;
  padding: 0.4vh 0.9vw;
  border-radius: 100vmax;
  font-size: 0.9vmax;
  flex-shrink: 0;
}
.status-chip .dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}
.status-chip.real {
  background: var(--app-color-green-light-5);
  color: var(--app-color-green-dark-2);
}
.status-chip.real .dot {
  background: var(--el-color-success);
}
.status-chip.mock {
  background: var(--app-color-blue-light-5);
  color: var(--app-text-color-secondary);
}
.status-chip.mock .dot {
  background: var(--app-text-color-placeholder);
}

.status-bar {
  margin-top: 1.6vh;
  display: flex;
  align-items: center;
  gap: 0.6vw;
  padding: 1vh 1vw;
  border-radius: 0.8vmax;
  font-size: 0.95vmax;
}
.status-bar.real {
  background: var(--app-color-green-light-5);
  color: var(--app-color-green-dark-2);
}
.status-bar.mock {
  background: var(--app-color-blue-light-5);
  color: var(--app-text-color-secondary);
}
.status-icon {
  font-size: 1.2vmax;
  flex-shrink: 0;
}
.status-message {
  flex: 1;
}

.switch-row {
  margin-top: 1.8vh;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1vw;
}
.switch-label {
  font-size: 1.05vmax;
  font-weight: bold;
}
.switch-hint {
  margin-top: 0.3vh;
  font-size: 0.85vmax;
  color: var(--app-text-color-secondary);
}

.field-block {
  margin-bottom: 1.4vh;
}
.field-label {
  margin-bottom: 1vh;
  font-size: 0.95vmax;
  color: var(--app-text-color-regular);
}
.field-hint {
  margin-top: 0.5vh;
  display: flex;
  align-items: center;
  gap: 0.4vw;
  font-size: 0.85vmax;
  color: var(--app-text-color-secondary);
  line-height: 1.4;
}
.rec-tag {
  margin-left: 0.3vw;
  padding: 0 0.3vw;
  font-size: 0.68vmax;
  font-style: normal;
  font-weight: 500;
  color: var(--app-color-primary);
  background: color-mix(in srgb, var(--app-color-primary) 12%, transparent);
  border-radius: 0.3vw;
}

/* ---- 供应商列表 ---- */
.list-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1vw;
  margin-bottom: 1.2vh;
}
.list-head .field-label {
  margin-bottom: 0.2vh;
}
.list-sub {
  font-size: 0.82vmax;
  color: var(--app-text-color-secondary);
}
.provider-list {
  display: flex;
  flex-direction: column;
  gap: 1vh;
}
.provider-item {
  display: flex;
  align-items: stretch;
  gap: 0.6vw;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 0.8vmax;
  padding: 1.2vh 1vw;
  transition: border-color 0.2s, background-color 0.2s, box-shadow 0.2s;
  cursor: pointer;
  /* 拖动时不选中卡片文字；需要复制时对具体值单独放开 */
  user-select: none;
  -webkit-user-select: none;
}
.provider-item:hover {
  box-shadow: 0 2px 10px rgba(0, 0, 0, 0.08);
}
/* 键盘聚焦时给出可见焦点圈 */
.provider-item:focus-visible {
  outline: 2px solid var(--app-color-purple);
  outline-offset: 2px;
}
.provider-item.active {
  border-color: var(--app-color-purple);
  background: var(--app-color-purple-light-5);
}
/* 拖动时的落位占位与跟手卡片 */
.drag-ghost {
  opacity: 0.35;
}
.drag-chosen {
  box-shadow: 0 6px 20px rgba(0, 0, 0, 0.16);
}
/* 拖拽把手：明确的按钮外观，且不参与文字选中 */
.drag-handle {
  display: flex;
  align-items: center;
  justify-content: center;
  align-self: center;
  width: 2vmax;
  height: 2vmax;
  border: 1px solid transparent;
  border-radius: 0.5vmax;
  background: transparent;
  font-size: 1.1vmax;
  color: var(--app-text-color-placeholder);
  cursor: grab;
  flex-shrink: 0;
  user-select: none;
  -webkit-user-select: none;
  transition: background-color 0.2s, color 0.2s;
}
.drag-handle:hover {
  background: var(--app-color-blue-light-5);
  color: var(--app-color-primary);
}
.drag-handle:active {
  cursor: grabbing;
}
.provider-body {
  flex: 1;
  min-width: 0;
}
.provider-top {
  display: flex;
  align-items: center;
  gap: 0.6vw;
  margin-bottom: 0.6vh;
}
.provider-name {
  font-size: 1vmax;
  font-weight: bold;
}
.provider-meta {
  display: flex;
  align-items: baseline;
  justify-content: flex-start;
  gap: 0.4vw;
  min-width: 0;
  overflow: hidden;
  font-size: 0.85vmax;
  color: var(--app-text-color-regular);
  line-height: 1.7;
  white-space: nowrap;
}
.meta-label {
  flex-shrink: 0;
  color: var(--app-text-color-placeholder);
  user-select: none;
}
/* 第二个及之后的标签前加分隔点 */
.meta-label:not(:first-child)::before {
  content: "·";
  margin-right: 0.4vw;
  color: var(--app-text-color-placeholder);
}
.meta-value {
  flex-shrink: 0;
  /* 允许手动复制地址/模型/Key */
  user-select: text;
  -webkit-user-select: text;
}
/* 地址不占满整行：模型 / Key 紧跟在它后面（过长时地址省略，完整值悬浮可见） */
.meta-url {
  flex: 0 1 auto;
  max-width: 38%;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
}
/* 右侧操作列：四个图标按钮，整体垂直居中 */
.provider-actions {
  display: flex;
  align-items: center;
  align-self: center;
  gap: 0.3vw;
  flex-shrink: 0;
}
/* Element Plus 相邻按钮自带 margin，会和 gap 叠加导致过宽 */
.provider-actions .el-button + .el-button {
  margin-left: 0;
}
/* 图标再放大一点，更易点中 */
.provider-actions :deep(.el-button) {
  font-size: 1.15vmax;
}
.action-danger:hover {
  color: var(--el-color-danger);
}

/* ---- 弹窗里的预设模板：单行触发 + 展开胶囊 ---- */
.preset-trigger {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.4vw;
  width: 100%;
  padding: 0.6vh 1vw;
  border-radius: 100vmax;
  border: 1px dashed var(--el-border-color);
  background: transparent;
  color: var(--app-text-color-regular);
  font-size: 0.95vmax;
  cursor: pointer;
  transition: all 0.2s;
}
.preset-trigger:hover {
  border-color: var(--app-color-purple);
  color: var(--app-color-purple);
}
.preset-trigger .el-icon {
  transition: transform 0.2s;
}
.preset-trigger .el-icon.open {
  transform: rotate(180deg);
}

/* ---- API Key：CSS 文本遮罩（避免 type=password 被密码管理器盯上） ---- */
.secret-masked :deep(input) {
  -webkit-text-security: disc;
  text-security: disc;
  letter-spacing: 0.08em;
}
.pwd-eye {
  cursor: pointer;
  color: var(--app-text-color-secondary);
}
.pwd-eye:hover {
  color: var(--app-color-primary);
}

/* ---- 模型名称：可搜索下拉 + 从上游获取按钮 ---- */
.model-field {
  display: flex;
  align-items: center;
  gap: 0.6vw;
  width: 100%;
}
.model-select,
.api-key-input {
  flex: 1;
  min-width: 0;
}
/* 候选项：左名称 + 右删除图标（hover 才显示，避免干扰） */
.model-option {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.8vw;
  width: 100%;
}
.model-option-label {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
}
.model-option-del {
  flex-shrink: 0;
  color: var(--app-text-color-placeholder);
  opacity: 0;
  transition: color 0.2s, opacity 0.2s;
}
/* 下拉是 teleport 到 body 的：作用域属性只加在最后一段选择器上，
   祖先用全局类名匹配即可生效 */
.el-select-dropdown__item:hover .model-option-del {
  opacity: 1;
}
.model-option-del:hover {
  color: var(--el-color-danger);
}
.preset-search {
  margin-bottom: 1vh;
}
.preset-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr)); /* 每行两个各占一半 */
  gap: 0.6vw;
  max-height: 46vh;
  overflow-y: auto; /* 超出滚动 */
}
.preset-chip {
  display: flex;
  align-items: center;
  gap: 0.4vw;
  min-width: 0;
  padding: 0.5vh 0.8vw;
  border-radius: 100vmax;
  border: 1px solid var(--el-border-color);
  background: transparent;
  color: var(--app-text-color-regular);
  font-size: 0.9vmax;
  cursor: pointer;
  transition: all 0.2s;
  text-align: left;
}
.preset-chip:hover {
  border-color: var(--app-color-purple);
  color: var(--app-color-purple);
}
.preset-chip.active {
  background: var(--app-color-purple-light-4);
  border-color: var(--app-color-purple);
  color: var(--app-color-purple-dark-1);
}
.preset-avatar {
  width: 1.6vmax;
  height: 1.6vmax;
  border-radius: 50%;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: var(--app-color-blue-light-5);
  overflow: hidden;
  flex-shrink: 0;
}
.preset-avatar img {
  width: 100%;
  height: 100%;
  object-fit: contain;
  display: block;
}
.preset-name {
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  flex-shrink: 0;
}
.preset-model {
  color: var(--app-text-color-placeholder);
  font-size: 0.8vmax;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  min-width: 0;
}
.preset-empty {
  grid-column: 1 / -1;
  padding: 1.2vh 0;
  font-size: 0.85vmax;
  color: var(--app-text-color-secondary);
  text-align: center;
}

.test-alert {
  margin-top: 1.2vh;
}

.actions {
  margin-top: 1.2vh;
  max-width: 640px;
  display: flex;
  justify-content: flex-end;
  gap: 0.8vw;
}

/* ---- 用户中心：头像区 ---- */
.account-avatar-row {
  display: flex;
  align-items: center;
  gap: 1vw;
  margin-bottom: 0.8vh;
}
.avatar-label {
  font-size: 0.95vmax;
  color: var(--app-text-color-regular);
  flex-shrink: 0;
}
.account-avatar-row :deep(.user-avatar) {
  flex-shrink: 0;
}
.avatar-hint {
  margin-bottom: 2vh;
}
.hidden-file {
  display: none;
}

/* 资料只读展示：昵称 / 账号 / 邮箱 */
.account-info {
  display: flex;
  flex-direction: column;
  gap: 1vh;
  padding: 1.2vh 1.2vw;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 0.8vmax;
  background: var(--app-color-blue-light-5);
  margin-bottom: 1.4vh;
}
.info-item {
  display: flex;
  align-items: center;
  gap: 1vw;
  font-size: 0.95vmax;
}
.info-label {
  flex-shrink: 0;
  min-width: 7em;
  white-space: nowrap;
  color: var(--app-text-color-secondary);
}
.info-value {
  color: var(--app-text-color-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.footnote {
  margin: 0;
  font-size: 0.85vmax;
  color: var(--app-text-color-secondary);
}

.setting-body {
  flex: 1;
  min-height: 0;
  display: flex;
  gap: 1.4vw;
  align-items: stretch;
}

.category-nav {
  width: 16vmax;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: 0.8vh;
  background-color: var(--app-color-white);
  border-radius: 1vmax;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.1);
  padding: 1.2vh 0.8vw;
  position: sticky;
  top: 0;
}

.category-item {
  display: flex;
  align-items: center;
  gap: 0.7vw;
  width: 100%;
  padding: 1.1vh 0.7vw;
  border: none;
  border-radius: 0.8vmax;
  background: transparent;
  cursor: pointer;
  text-align: left;
  transition: all 0.2s;
}
.category-item:hover {
  background: var(--app-color-blue-light-5);
}
.category-item.active {
  background: linear-gradient(
    135deg,
    var(--app-color-blue-light-5),
    var(--app-color-purple-light-5)
  );
}

.category-icon {
  width: 2.4vmax;
  height: 2.4vmax;
  border-radius: 0.7vmax;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1.3vmax;
  color: var(--app-color-white);
  background: linear-gradient(135deg, var(--app-color-blue), var(--app-color-purple));
  flex-shrink: 0;
}
.category-item.active .category-icon {
  background: linear-gradient(135deg, var(--app-color-purple), var(--app-color-blue));
}

.category-meta {
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.category-label {
  font-size: 1.05vmax;
  font-weight: bold;
  color: var(--app-text-color-primary);
}
.category-desc {
  font-size: 0.78vmax;
  color: var(--app-text-color-secondary);
  margin-top: 0.2vh;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.category-content {
  flex: 1;
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 2vh;
}
</style>
