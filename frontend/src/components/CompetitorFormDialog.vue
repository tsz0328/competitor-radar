<script setup lang="ts">
import { computed, reactive, ref, watch } from "vue";
import { ElMessage, type FormInstance, type FormRules } from "element-plus";
import { Check, Delete, InfoFilled, Link } from "@element-plus/icons-vue";
import { useCompetitorStore } from "@/stores/competitor";
import CompetitorLogo from "@/components/CompetitorLogo.vue";
import { fetchSourceTypes } from "@/api/competitor";
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

const form = reactive({
  name: "",
  officialUrl: "",
  category: "",
  description: "",
});

const categoryOptions = [
  "SaaS工具",
  "AI产品",
  "协作办公",
  "消费品牌",
  "开发者工具",
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

// 默认勾选对"竞品监控"最有价值的三类页面
const DEFAULT_SELECTED: SourceType[] = ["homepage", "pricing", "changelog"];

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
  return (v.startsWith("http") ? v : `https://${v}`).replace(/\/+$/, "");
}

const previewDomain = computed(
  () => normalizeBaseUrl(form.officialUrl).split("//")[1] ?? "",
);

function guessUrl(type: SourceType): string {
  return normalizeBaseUrl(form.officialUrl) + (PATH_GUESS[type] ?? "");
}

function labelOf(type: SourceType): string {
  return typeOptions.value.find((o) => o.type === type)?.label ?? type;
}

function humanize(minutes: number): string {
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
  selected.value = selected.value.filter((t) => t !== type);
  delete urls[type];
  delete intervals[type];
}

function toggleType(opt: SourceTypeOption) {
  if (isSelected(opt.type)) {
    removeType(opt.type);
    return;
  }
  selected.value = [...selected.value, opt.type];
  urls[opt.type] = guessUrl(opt.type);
  intervals[opt.type] = opt.defaultIntervalMinutes;
}

/** 用户没手填名称时，从官网域名猜一个品牌名 */
function guessNameFromUrl() {
  if (form.name.trim() || !previewDomain.value) return;
  const core = previewDomain.value.replace(/^www\./, "").split(".")[0];
  if (core) form.name = core.charAt(0).toUpperCase() + core.slice(1);
}

function onUrlBlur() {
  guessNameFromUrl();
  // 官网地址变了，同步刷新各页面的预填地址
  selected.value.forEach((type) => {
    urls[type] = guessUrl(type);
  });
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
  Object.assign(form, { name: "", officialUrl: "", category: "", description: "" });
  selected.value = [];
  Object.keys(urls).forEach((key) => delete urls[key]);
  Object.keys(intervals).forEach((key) => delete intervals[key]);
  submitting.value = false;
}

function applyDefaults() {
  DEFAULT_SELECTED.forEach((type) => {
    const opt = typeOptions.value.find((o) => o.type === type);
    if (!opt) return;
    selected.value.push(type);
    urls[type] = "";
    intervals[type] = opt.defaultIntervalMinutes;
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
  });
}

async function initialize() {
  resetForm();
  await loadTypeOptions();
  if (props.competitor) {
    applyCompetitor(props.competitor);
    if (!selected.value.length) applyDefaults(); // 历史数据可能没有监控源，兜底
  } else {
    applyDefaults();
  }
}

watch(visible, (open) => {
  if (open) initialize();
});

function buildPayload(): CompetitorCreatePayload {
  const sources: MonitorSourceInput[] = selected.value.map((type) => ({
    sourceType: type,
    url: (urls[type] || guessUrl(type)) || undefined,
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

async function handleSubmit() {
  const valid = await formRef.value?.validate().catch(() => false);
  if (!valid) return;
  submitting.value = true;
  try {
    const payload = buildPayload();
    if (props.competitor) {
      await store.editCompetitor(props.competitor.id, payload);
      ElMessage.success("修改已保存");
    } else {
      await store.addCompetitor(payload);
      ElMessage.success("竞品已添加，开始监控");
    }
    visible.value = false;
  } finally {
    submitting.value = false;
  }
}

const footerTip = computed(() =>
  isEdit.value
    ? `保存后按此配置同步监控源（共 ${selected.value.length || 1} 个）`
    : `将创建 ${selected.value.length || 1} 个监控源，可稍后在详情中调整`,
);
</script>

<template>
  <el-dialog
    v-model="visible"
    :title="isEdit ? '编辑竞品' : '新增竞品'"
    width="min(720px, 92vw)"
    :close-on-click-modal="false"
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
        <CompetitorLogo
          :name="form.name"
          :domain="form.officialUrl"
          :size="56"
          class="brand-logo"
        />

        <div class="brand-fields">
          <el-form-item label="竞品名称" prop="name" class="flex-1">
            <el-input
              v-model="form.name"
              placeholder="如 Notion"
              maxlength="100"
              clearable
            />
          </el-form-item>
          <el-form-item label="官网地址" prop="officialUrl" class="flex-1">
            <el-input
              v-model="form.officialUrl"
              placeholder="如 https://notion.so"
              clearable
              :prefix-icon="Link"
              @blur="onUrlBlur"
            />
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
          @click="toggleType(opt)"
        >
          <span class="type-label">{{ opt.label }}</span>
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
          />
          <el-select v-model="intervals[type]" size="small" class="source-interval">
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
          <el-button @click="visible = false">取消</el-button>
          <el-button type="primary" :loading="submitting" @click="handleSubmit">
            {{ isEdit ? "保存修改" : "立即创建" }}
          </el-button>
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
.brand-logo {
  margin-top: 2.6vh;
  border-radius: 0.8vmax;
  background: var(--app-color-blue-light-5);
  color: var(--app-color-blue-dark-2);
  font-weight: 600;
  flex-shrink: 0;
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
</style>
