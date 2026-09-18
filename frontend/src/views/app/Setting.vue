<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import {
  Check,
  CircleCheckFilled,
  Connection,
  Cpu,
  InfoFilled,
  Key,
  Link,
  Setting as SettingIcon,
} from "@element-plus/icons-vue";
import {
  fetchLlmSetting,
  testLlmSetting,
  updateLlmSetting,
  type LlmSetting,
  type LlmSettingUpdate,
  type LlmTestResult,
} from "@/api/setting";
import { fetchSourceTypes } from "@/api/competitor";
import type { SourceType, SourceTypeOption } from "@/types/competitor";
import { useLlmStore } from "@/stores/llm";

const llmStore = useLlmStore();

/** 设置分类：左侧导航，右侧渲染对应分类内容，便于后续扩展更多分类 */
const categories = [
  { key: "ai", label: "AI 模型", desc: "模型接入与连通性", icon: Cpu },
  {
    key: "preferences",
    label: "添加竞品偏好",
    desc: "官网校验与默认勾选",
    icon: SettingIcon,
  },
] as const;
const activeCategory = ref<(typeof categories)[number]["key"]>("ai");

// 添加竞品偏好：与 CompetitorFormDialog 共用同一个 localStorage key
const ALLOW_UNREACHABLE_KEY = "competitor.allowUnreachableOfficial";
const allowUnreachableOfficial = ref(
  localStorage.getItem(ALLOW_UNREACHABLE_KEY) === "1",
);
watch(allowUnreachableOfficial, (v) => {
  localStorage.setItem(ALLOW_UNREACHABLE_KEY, v ? "1" : "0");
  ElMessage.success(
    v ? "已开启：官网不可达也可先创建" : "已关闭：官网不可达将拦截保存",
  );
});

// 新增竞品默认勾选的监控页面（与 CompetitorFormDialog 共用 localStorage key）
const DEFAULT_TYPES_KEY = "competitor.defaultSelectedTypes";
// 推荐优先勾选的页面（对竞品监控价值更高）
const RECOMMENDED_TYPES = new Set<SourceType>(["pricing", "changelog"]);
const typeOptions = ref<SourceTypeOption[]>([]);
function readDefaultTypes(): SourceType[] {
  try {
    const raw = localStorage.getItem(DEFAULT_TYPES_KEY);
    if (raw) {
      const arr = JSON.parse(raw);
      if (Array.isArray(arr) && arr.length) return arr as SourceType[];
    }
  } catch {
    /* ignore */
  }
  return ["homepage"];
}
const defaultSelectedTypes = ref<SourceType[]>(readDefaultTypes());
watch(
  defaultSelectedTypes,
  (v) => {
    localStorage.setItem(DEFAULT_TYPES_KEY, JSON.stringify(v));
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

/** 常见服务商预设：点一下自动填好地址与模型，降低配置门槛 */
const PROVIDER_PRESETS = [
  { key: "deepseek", label: "DeepSeek", baseUrl: "https://api.deepseek.com/v1", model: "deepseek-chat" },
  { key: "glm", label: "智谱 GLM", baseUrl: "https://open.bigmodel.cn/api/paas/v4", model: "glm-4-flash" },
  { key: "kimi", label: "Kimi", baseUrl: "https://api.moonshot.cn/v1", model: "moonshot-v1-8k" },
  { key: "ark", label: "火山方舟", baseUrl: "https://ark.cn-beijing.volces.com/api/v3", model: "" },
  { key: "custom", label: "自定义", baseUrl: "", model: "" },
];

const form = reactive({
  enabled: false,
  baseUrl: "",
  model: "",
  apiKey: "",
  timeoutSeconds: 30,
  minChangeLines: 3,
});

/** 自定义值快照：记住"非预设"的地址与模型，切走预设再切回自定义时用于还原 */
const customSnapshot = reactive({ baseUrl: "", model: "" });

const hasApiKey = ref(false);
const apiKeyPreview = ref("");
const source = ref<"database" | "env">("env");
const mode = ref<"real" | "mock">("mock");
const statusMessage = ref("");

const loading = ref(false);
const saving = ref(false);
const testing = ref(false);
const testResult = ref<LlmTestResult | null>(null);

/** 命中的预设（按地址匹配），用于高亮；不匹配任何已知预设即视为自定义 */
const activePreset = computed(() => {
  const url = form.baseUrl.trim().replace(/\/+$/, "");
  const matched = PROVIDER_PRESETS.find(
    (p) => p.baseUrl && p.baseUrl.replace(/\/+$/, "") === url,
  );
  return matched ? matched.key : "custom";
});

/** 当前是否已有一把可用 Key（已保存且未清除，或本次新填） */
const effectiveHasKey = computed(
  () => hasApiKey.value || !!form.apiKey.trim(),
);
const canEnable = computed(
  () => effectiveHasKey.value && !!form.baseUrl.trim() && !!form.model.trim(),
);

const apiKeyPlaceholder = computed(() => {
  if (hasApiKey.value) return `已保存：${apiKeyPreview.value}（如需替换请直接填写）`;
  return "请输入 API Key";
});

function applyData(data: LlmSetting) {
  form.enabled = data.enabled;
  form.baseUrl = data.baseUrl;
  form.model = data.model;
  // 以已保存的值为自定义基线，切走预设再切回自定义时还原
  customSnapshot.baseUrl = data.baseUrl;
  customSnapshot.model = data.model;
  form.timeoutSeconds = data.timeoutSeconds;
  form.minChangeLines = data.minChangeLines;
  hasApiKey.value = data.hasApiKey;
  apiKeyPreview.value = data.apiKeyPreview;
  source.value = data.source;
  mode.value = data.mode;
  statusMessage.value = data.message;
  // 保存成功后保留输入框里已填的 Key（与其他字段一致，留在框内）
  form.apiKey = data.hasApiKey ? form.apiKey : "";
  testResult.value = null;
}

async function load() {
  loading.value = true;
  try {
    applyData(await fetchLlmSetting());
  } catch {
    // 错误提示由 request.ts 统一弹出
  } finally {
    loading.value = false;
  }
}

function applyPreset(preset: (typeof PROVIDER_PRESETS)[number]) {
  if (preset.key === "custom") {
    // 自定义：还原上一次保存/手填的地址与模型，而不是清空
    form.baseUrl = customSnapshot.baseUrl;
    form.model = customSnapshot.model;
  } else {
    // 已知预设：地址一定有；模型按预设填充（为空则清空，避免沿用上一个自定义的模型）
    form.baseUrl = preset.baseUrl;
    form.model = preset.model;
  }
  testResult.value = null;
}

async function save() {
  if (form.enabled && !canEnable.value) {
    ElMessage.warning("启用前请先填写 API 地址、模型名称与 API Key");
    return;
  }
  saving.value = true;
  try {
    const payload: LlmSettingUpdate = {
      enabled: form.enabled,
      baseUrl: form.baseUrl.trim(),
      model: form.model.trim(),
      timeoutSeconds: form.timeoutSeconds,
      minChangeLines: form.minChangeLines,
    };
    if (form.apiKey.trim()) payload.apiKey = form.apiKey.trim();

    applyData(await updateLlmSetting(payload));
    ElMessage.success("设置已保存并即时生效");
    llmStore.refresh();
  } catch {
    // 错误提示由 request.ts 统一弹出
  } finally {
    saving.value = false;
  }
}

async function test() {
  testing.value = true;
  testResult.value = null;
  try {
    testResult.value = await testLlmSetting({
      baseUrl: form.baseUrl.trim() || undefined,
      model: form.model.trim() || undefined,
      // 未填则后端用已保存的 Key 测试
      apiKey: form.apiKey.trim() || undefined,
      timeoutSeconds: form.timeoutSeconds,
    });
  } catch {
    // 错误提示由 request.ts 统一弹出
  } finally {
    testing.value = false;
  }
}

onMounted(() => {
  load();
  loadTypes();
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
            <el-switch v-model="form.enabled" />
          </div>

          <el-divider />

          <div class="field-block">
            <div class="field-label">服务商预设</div>
            <div class="preset-row">
              <button
                v-for="preset in PROVIDER_PRESETS"
                :key="preset.key"
                type="button"
                class="preset-chip"
                :class="{ active: activePreset === preset.key }"
                @click="applyPreset(preset)"
              >
                {{ preset.label }}
              </button>
            </div>
          </div>

          <el-form label-position="top" class="form">
            <el-form-item label="API 地址">
              <el-input
                v-model="form.baseUrl"
                placeholder="https://api.deepseek.com/v1"
                clearable
                @input="customSnapshot.baseUrl = form.baseUrl"
              >
                <template #prefix><el-icon><Link /></el-icon></template>
              </el-input>
            </el-form-item>

            <el-form-item label="模型名称">
              <el-input
                v-model="form.model"
                placeholder="如 deepseek-chat / glm-4-flash / moonshot-v1-8k"
                clearable
                @input="customSnapshot.model = form.model"
              >
                <template #prefix><el-icon><Cpu /></el-icon></template>
              </el-input>
            </el-form-item>

            <el-form-item label="API Key">
              <el-input
                v-model="form.apiKey"
                type="password"
                show-password
                clearable
                :placeholder="apiKeyPlaceholder"
              >
                <template #prefix><el-icon><Key /></el-icon></template>
              </el-input>
            </el-form-item>
          </el-form>

          <div class="actions">
            <el-button :icon="Connection" :loading="testing" @click="test">
              测试连接
            </el-button>
            <el-button
              type="primary"
              :icon="Check"
              :loading="saving"
              @click="save"
            >
              保存设置
            </el-button>
          </div>

          <el-alert
            v-if="testResult"
            class="test-alert"
            :type="testResult.ok ? 'success' : 'error'"
            :closable="false"
            show-icon
            :title="testResult.message"
          />
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
      </div>
    </div>

    <p class="footnote">
      提示：API Key 仅保存在你的服务器本地数据库，接口只回传脱敏预览，不会写入日志。
    </p>
  </div>
</template>

<style scoped>
.setting-page {
  height: 100%;
  overflow-y: auto;
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
.preset-row {
  display: flex;
  flex-wrap: wrap;
  gap: 0.6vw;
}
.preset-chip {
  padding: 0.6vh 1vw;
  border-radius: 100vmax;
  border: 1px solid var(--el-border-color);
  background: transparent;
  color: var(--app-text-color-regular);
  font-size: 0.95vmax;
  cursor: pointer;
  transition: all 0.2s;
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

.form {
  max-width: 640px;
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
.field-hint.danger {
  color: var(--el-color-danger);
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
  align-items: flex-start;
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
  display: flex;
  flex-direction: column;
  gap: 2vh;
}
</style>
