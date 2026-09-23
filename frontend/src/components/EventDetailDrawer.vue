<script setup lang="ts">
/**
 * 情报事件详情抽屉：事件流页与 Dashboard 共用。
 *
 * 数据由 event store 统一加载，父组件只需给出 eventId 并控制显隐，
 * 不必各自重复实现"拉详情 + 差异着色 + 布局"。
 *
 * 额外能力：在详情内展示"相关事件"（同竞品其它近期事件），
 * 点击后通过 select 事件通知父组件切换 eventId，复用现有 watch 重新加载。
 */
import { computed, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { Close, Download } from "@element-plus/icons-vue";
import { useEventStore } from "@/stores/event";
import CompetitorLogo from "@/components/CompetitorLogo.vue";
import { fetchEventSnapshots, fetchSnapshotRaw } from "@/api/event";
import { exportEventMarkdown } from "@/utils/exportEvents";
import type { EventSnapshot } from "@/types/event";

const props = defineProps<{
  modelValue: boolean;
  /** 要展示的事件 id；为 null 时不请求 */
  eventId: number | null;
}>();
const emit = defineEmits<{
  (e: "update:modelValue", value: boolean): void;
  (e: "select", id: number): void;
  /** 主详情加载成功时触发，携带事件 id；父组件据此（如从通知跳入）标记已读 */
  (e: "loaded", id: number): void;
}>();

const eventStore = useEventStore();
const router = useRouter();

/** 详情里的竞品名 → 竞品管理（带 competitorId 定位） */
function goToCompetitor() {
  const id = detail.value?.competitorId;
  if (id) router.push({ name: "Competitor", query: { competitorId: String(id) } });
}

/** 导出本条情报事件为 Markdown */
function onExportDetail() {
  if (!detail.value) return;
  exportEventMarkdown(detail.value);
}

const visible = computed({
  get: () => props.modelValue,
  set: (value) => emit("update:modelValue", value),
});

const detail = computed(() => eventStore.eventDetail);

/** 把 unified diff 拆行渲染，按行着色 */
const diffLines = computed(() => (detail.value?.diffDetail ?? "").split("\n"));

function diffLineClass(line: string): string {
  if (line.startsWith("+++") || line.startsWith("---")) return "diff-file";
  if (line.startsWith("@@")) return "diff-hunk";
  if (line.startsWith("+")) return "diff-add";
  if (line.startsWith("-")) return "diff-del";
  return "diff-ctx";
}

// 相关事件筛选：时间范围 + 类型
const categoryOptions = [
  { value: "feature", label: "功能更新" },
  { value: "price", label: "价格变化" },
  { value: "content", label: "内容更新" },
  { value: "negative", label: "舆论动态" },
  { value: "other", label: "其他" },
];
const relatedDays = ref<string>("");
const relatedCategory = ref<string>("");

// ---- 历史快照：证据链的最后一环（结论 → 分析 → Diff → 原始页面） ----
const snapshots = ref<EventSnapshot[]>([]);
const snapshotsLoading = ref(false);

async function loadSnapshots(id: number) {
  snapshots.value = [];
  snapshotsLoading.value = true;
  try {
    snapshots.value = await fetchEventSnapshots(id);
  } catch {
    snapshots.value = [];
  } finally {
    snapshotsLoading.value = false;
  }
}

const snapshotOpen = ref(false);
const snapshotLoading = ref(false);
const snapshotHtml = ref("");
const snapshotLabel = ref("");

async function openSnapshot(item: EventSnapshot) {
  snapshotLabel.value = `${item.crawledAtLabel}${
    item.changeDetected ? " · 检测到变化" : " · 基准"
  }`;
  snapshotHtml.value = "";
  snapshotOpen.value = true;
  snapshotLoading.value = true;
  try {
    snapshotHtml.value = await fetchSnapshotRaw(item.id);
  } catch {
    snapshotHtml.value = "";
  } finally {
    snapshotLoading.value = false;
  }
}

async function loadDetail(id: number) {
  try {
    const d = await eventStore.loadEventDetail(id);
    // 主详情拿到即通知父组件（从通知跳入时在此标记已读），
    // 不再等次要数据，避免「主详情已成功、次要请求挂了」被误判成整体失败。
    // 仅在确有数据时才 emit（陈旧请求被取代时 d 为 undefined，不触发标记已读）。
    if (d) emit("loaded", id);
    // 打开新事件时重置筛选，再拉取相关事件
    relatedDays.value = "";
    relatedCategory.value = "";
    if (d?.competitorId) {
      // 相关事件失败不应关掉抽屉：它们只是侧栏补充，主内容已就绪
      try {
        await eventStore.loadRelatedEvents(d.competitorId, id);
      } catch {
        /* 侧栏留空即可，不向上抛 */
      }
    }
    // 历史快照失败已在 loadSnapshots 内部消化（catch 内清空），这里不抛
    await loadSnapshots(id);
  } catch {
    // 仅「主详情」失败才落到这里。注意：**不关闭抽屉**，
    // 让模板的 v-else 兜底显示「没能加载 + 重试」，用户可原地重试。
    // 失败提示 toast 仍由 request.ts 拦截器统一弹出。
  }
}

/** 原地重试：主详情加载失败时，用户在错误态点击「重试」 */
function retryLoad() {
  if (props.eventId != null) loadDetail(props.eventId);
}

/** 点击相关事件：通知父组件切换 eventId（由其 watch 重新加载详情+相关事件） */
function selectRelated(id: number) {
  emit("select", id);
}

/** 按当前筛选条件重新拉取相关事件 */
function reloadRelated() {
  const d = detail.value;
  if (!d?.competitorId || d.id == null) return;
  eventStore.loadRelatedEvents(d.competitorId, d.id, {
    days: relatedDays.value ? Number(relatedDays.value) : undefined,
    category: relatedCategory.value || undefined,
  });
}

// 打开时加载；已打开的情况下切换事件也重新加载。
// immediate 是关键：从通知/周报等深链跳进来时，父组件（Event.vue 的 applyQuery）
// 会在 setup 阶段就同时设好 eventId 与 modelValue=true，子组件「挂载即已打开」。
// 若 watch 不在挂载时触发，这条路径就永远不请求详情，抽屉一直停在「没能加载」，
// 必须手点重试才恢复。immediate 让「挂载即打开」也立即加载。
watch(
  () => [props.modelValue, props.eventId] as const,
  ([open, id]) => {
    if (open && id != null) loadDetail(id);
  },
  { immediate: true },
);
</script>

<template>
  <el-drawer
    v-model="visible"
    :with-header="false"
    size="min(760px, 94vw)"
    class="event-detail-drawer"
  >
    <div class="detail-body">
      <!-- 加载中给骨架屏：从通知/周报带 id 跳进来时抽屉会立刻滑出，详情还在路上，
           原先只有一个居中转圈，整块抽屉看起来就是"半屏白板" -->
      <el-skeleton v-if="eventStore.detailLoading" animated>
        <template #template>
          <div class="sk-head">
            <el-skeleton-item variant="image" class="sk-logo" />
            <div class="sk-head-main">
              <el-skeleton-item variant="h3" style="width: 45%" />
              <el-skeleton-item variant="text" style="width: 70%" />
            </div>
          </div>
          <el-skeleton-item variant="h3" style="width: 82%; margin-top: 2.5vh" />
          <el-skeleton-item variant="text" style="width: 100%; margin-top: 1.2vh" />
          <el-skeleton-item variant="text" style="width: 94%; margin-top: 0.8vh" />
          <el-skeleton-item variant="text" style="width: 58%; margin-top: 0.8vh" />
        </template>
      </el-skeleton>

      <template v-else-if="detail">
        <header class="detail-head">
          <!-- 与列表/其它页面共用同一套竞品图标（多级回退） -->
          <CompetitorLogo
            :name="detail.brand"
            :domain="detail.domain"
            :src="detail.logoUrl"
            :size="48"
          />
          <div class="detail-head-main">
            <div class="detail-brand-row">
              <span
                class="detail-brand brand-link"
                title="查看竞品"
                @click="goToCompetitor"
                >{{ detail.brand }}</span
              >
              <span class="event-tag" :class="detail.tagType">{{
                detail.tag
              }}</span>
              <span class="priority-tag" :class="detail.priorityType">{{
                detail.priority
              }}</span>
            </div>
            <div class="detail-sub">
              {{ detail.date }} {{ detail.time }} · {{ detail.ago }} · 来源：{{
                detail.source
              }}
            </div>
          </div>
          <el-button
            link
            :icon="Download"
            :disabled="!detail"
            @click="onExportDetail"
            >导出</el-button
          >
          <el-button link :icon="Close" @click="visible = false" />
        </header>

        <section class="detail-section">
          <div class="detail-title">{{ detail.title }}</div>
          <p class="detail-summary">{{ detail.summary }}</p>
          <div v-if="detail.keywords?.length" class="detail-keywords">
            <span v-for="k in detail.keywords" :key="k" class="keyword">{{
              k
            }}</span>
          </div>
        </section>

        <section v-if="detail.aiAnalysis" class="detail-section">
          <div class="detail-section-title ai-title">
            AI 判断
            <span class="ai-badge">仅供参考</span>
          </div>
          <p class="detail-analysis">{{ detail.aiAnalysis }}</p>
        </section>

        <section class="detail-section">
          <div class="detail-section-title">事件信息</div>
          <div class="meta-grid">
            <div class="meta-item">
              <span class="meta-label">事件类型</span>
              <span>{{ detail.tag }}</span>
            </div>
            <div class="meta-item">
              <span class="meta-label">优先级</span>
              <span class="priority-text" :class="detail.priorityType">{{
                detail.priority
              }}</span>
            </div>
            <div class="meta-item">
              <span class="meta-label">AI 置信度</span>
              <span class="meta-confidence">
                <el-progress
                  :percentage="detail.aiConfidence"
                  :show-text="false"
                  color="#22c55e"
                />
                <b>{{ detail.aiConfidence }}%</b>
              </span>
            </div>
            <div class="meta-item">
              <span class="meta-label">检测时间</span>
              <span>{{ detail.date }} {{ detail.time }}</span>
            </div>
            <div class="meta-item">
              <span class="meta-label">监控页面</span>
              <a
                v-if="detail.sourceUrl"
                :href="detail.sourceUrl"
                target="_blank"
                rel="noreferrer"
                class="meta-link"
                >{{ detail.sourceUrl }}</a
              >
              <span v-else>{{ detail.source }}</span>
            </div>
            <div class="meta-item">
              <span class="meta-label">竞品官网</span>
              <a
                v-if="detail.url"
                :href="detail.url"
                target="_blank"
                rel="noreferrer"
                class="meta-link"
                >{{ detail.domain }}</a
              >
              <span v-else>—</span>
            </div>
          </div>
        </section>

        <section class="detail-section">
          <div class="detail-section-title">
            变化内容
            <span class="detail-hint">+ 新增 / - 删除</span>
          </div>
          <pre v-if="detail.diffDetail" class="diff-view"><code><span
              v-for="(line, idx) in diffLines"
              :key="idx"
              class="diff-line"
              :class="diffLineClass(line)"
            >{{ line || " " }}</span></code></pre>
          <div v-else class="detail-empty">这条事件没有留存差异内容</div>
        </section>

        <section class="detail-section">
          <div class="detail-section-title">
            历史快照
            <span class="detail-hint">抓取当时留存的原始页面</span>
          </div>
          <div v-if="snapshotsLoading" class="detail-empty">加载中…</div>
          <ul v-else-if="snapshots.length" class="snap-list">
            <li v-for="item in snapshots" :key="item.id" class="snap-item">
              <span class="snap-time">{{ item.crawledAtLabel }}</span>
              <span class="snap-tag" :class="{ changed: item.changeDetected }">
                {{ item.changeDetected ? "检测到变化" : "基准" }}
              </span>
              <span v-if="item.isCurrent" class="snap-tag current">本条事件</span>
              <el-button
                class="snap-btn"
                link
                :disabled="!item.available"
                @click="openSnapshot(item)"
              >
                {{ item.available ? "查看快照" : "未留存" }}
              </el-button>
            </li>
          </ul>
          <div v-else class="detail-empty">该监控页面暂无历史快照</div>
        </section>

        <section class="detail-section">
          <div class="detail-section-title">
            相关事件
            <span class="rel-filter">
              <select v-model="relatedDays" class="rel-select" @change="reloadRelated">
                <option value="">全部时间</option>
                <option value="7">近 7 天</option>
                <option value="30">近 30 天</option>
              </select>
              <select v-model="relatedCategory" class="rel-select" @change="reloadRelated">
                <option value="">全部类型</option>
                <option v-for="c in categoryOptions" :key="c.value" :value="c.value">
                  {{ c.label }}
                </option>
              </select>
            </span>
          </div>
          <div v-if="eventStore.relatedLoading" class="detail-empty">加载中…</div>
          <ul v-else-if="eventStore.relatedEvents.length" class="related-list">
            <li
              v-for="r in eventStore.relatedEvents"
              :key="r.id"
              class="related-item"
              @click="selectRelated(r.id)"
            >
              <div class="related-title">{{ r.title }}</div>
              <div class="related-meta">
                <span class="related-tag">{{ r.tag }}</span>
                <span class="priority-text" :class="r.priorityType">{{ r.priority }}</span>
                <span class="related-date">{{ r.date }}</span>
              </div>
            </li>
          </ul>
          <div v-else class="detail-empty">暂无相关事件</div>
        </section>
      </template>

      <!-- 既没详情也不在加载：通常是接口失败（错误提示由 request.ts 统一弹出） -->
      <div v-else class="detail-empty">
        <p>没能加载这条情报，请稍后重试</p>
        <el-button type="primary" size="small" @click="retryLoad">
          重试
        </el-button>
      </div>
    </div>
  </el-drawer>

  <!-- 历史快照：sandbox iframe 内查看，抓来的页面不会执行脚本 -->
  <el-dialog
    v-model="snapshotOpen"
    :title="`历史快照 · ${snapshotLabel}`"
    width="80%"
    top="5vh"
    class="snapshot-dialog"
  >
    <div v-loading="snapshotLoading" class="snap-view">
      <iframe
        v-if="snapshotHtml"
        class="snap-frame"
        sandbox=""
        :srcdoc="snapshotHtml"
      />
      <div v-else-if="!snapshotLoading" class="detail-empty">快照内容为空</div>
    </div>
  </el-dialog>
</template>

<style scoped>
.detail-body {
  min-height: 240px;
}

/* 骨架屏：头部占位对齐真实布局（4vmax 图标 + 两行文字） */
.sk-head {
  display: flex;
  align-items: center;
  gap: 1vw;
  padding-bottom: 1.5vh;
}

.sk-logo {
  width: 4vmax;
  height: 4vmax;
  min-width: 44px;
  min-height: 44px;
  border-radius: 0.6vmax;
}

.sk-head-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 1.2vh;
}

.detail-head {
  display: flex;
  align-items: center;
  gap: 1vw;
  padding-bottom: 1.5vh;
  border-bottom: 1px solid #f0f0f0;
}

.detail-head-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 0.5vh;
}

.detail-brand-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 0.6vw;
}

.detail-brand {
  font-size: 1.3vmax;
  font-weight: bold;
}
.brand-link {
  cursor: pointer;
  transition: color 0.15s;
}
.brand-link:hover {
  color: var(--app-color-primary);
  text-decoration: underline;
}

.detail-sub {
  font-size: 0.95vmax;
  color: var(--app-color-gray);
}

.detail-section {
  margin-top: 2.5vh;
}

.detail-section-title {
  display: flex;
  align-items: baseline;
  gap: 0.6vw;
  font-size: 1.05vmax;
  font-weight: bold;
  margin-bottom: 1vh;
  padding-left: 0.6vw;
  border-left: 3px solid var(--app-color-primary);
}

.detail-hint {
  font-size: 0.85vmax;
  font-weight: normal;
  color: var(--app-color-gray);
}

.detail-title {
  font-size: 1.25vmax;
  font-weight: bold;
  line-height: 1.6;
}

.detail-summary {
  margin: 1vh 0 0;
  font-size: 1.05vmax;
  line-height: 1.75;
}

.detail-keywords {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5vw;
  margin-top: 1.2vh;
}

/* AI 判断区块：与事实摘要视觉区分，强调"仅供参考" */
.ai-title {
  border-left-color: #8b5cf6;
}

.ai-badge {
  font-size: 0.75vmax;
  font-weight: normal;
  color: #8b5cf6;
  background: #f3eefe;
  border: 1px solid #e0d4fb;
  border-radius: 0.4vmax;
  padding: 0.1vh 0.5vw;
  margin-left: 0.4vw;
}

.detail-analysis {
  margin: 1vh 0 0;
  font-size: 1.05vmax;
  line-height: 1.75;
  color: #5b21b6;
  background: #faf7ff;
  border: 1px solid #ece4fb;
  border-radius: 0.8vmax;
  padding: 1.2vh 1vw;
}

/* 事件信息网格 */
.meta-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 1.2vh 1.5vw;
}

.meta-item {
  display: flex;
  flex-direction: column;
  gap: 0.4vh;
  font-size: 1vmax;
  min-width: 0;
}

.meta-label {
  font-size: 0.9vmax;
  color: var(--app-color-gray);
}

.meta-confidence {
  display: flex;
  align-items: center;
  gap: 0.6vw;
}

.meta-confidence :deep(.el-progress) {
  flex: 1;
  max-width: 140px;
}

.meta-link {
  color: var(--app-color-primary);
  text-decoration: none;
  word-break: break-all;
}

.meta-link:hover {
  text-decoration: underline;
}

.priority-text.high {
  color: #ff4d4f;
}
.priority-text.mid {
  color: #fa8c16;
}
.priority-text.low {
  color: #22c55e;
}

/* 差异视图：按行着色 */
.diff-view {
  margin: 0;
  padding: 1.2vh 1vw;
  max-height: 42vh;
  overflow: auto;
  background: #fafafa;
  border: 1px solid #f0f0f0;
  border-radius: 0.8vmax;
  font-family: Consolas, Menlo, "Courier New", monospace;
  font-size: 0.92vmax;
  line-height: 1.7;
}

.diff-line {
  display: block;
  white-space: pre-wrap;
  word-break: break-all;
  padding: 0 0.4vw;
}

.diff-add {
  background: #e8f8ee;
  color: #12805a;
}
.diff-del {
  background: #fdecec;
  color: #c81e4a;
}
.diff-hunk,
.diff-file {
  color: #8c8c8c;
}
.diff-file {
  font-weight: bold;
}
.diff-ctx {
  color: #595959;
}

.detail-empty {
  padding: 2vh 1vw;
  font-size: 1vmax;
  color: var(--app-color-gray);
  background: #fafafa;
  border-radius: 0.8vmax;
}

/* 相关事件列表 */
.related-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.8vh;
}

.related-item {
  padding: 1vh 1vw;
  border: 1px solid #f0f0f0;
  border-radius: 0.6vmax;
  cursor: pointer;
  transition: background 0.15s, border-color 0.15s;
}

.related-item:hover {
  background: #f7f9ff;
  border-color: var(--app-color-primary);
}

.related-title {
  font-size: 1vmax;
  font-weight: 500;
  line-height: 1.5;
}

.related-meta {
  display: flex;
  align-items: center;
  gap: 0.8vw;
  margin-top: 0.4vh;
  font-size: 0.85vmax;
  color: var(--app-color-gray);
}

.related-tag {
  color: var(--app-color-primary);
}

/* 相关事件筛选 */
.rel-filter {
  display: inline-flex;
  gap: 0.6vw;
  font-weight: normal;
}

.rel-select {
  font-size: 0.85vmax;
  padding: 0.3vh 0.5vw;
  border: 1px solid #e5e5e5;
  border-radius: 0.4vmax;
  background: #fff;
  color: var(--app-color-gray);
  cursor: pointer;
}

/* 历史快照列表 */
.snap-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.6vh;
}

.snap-item {
  display: flex;
  align-items: center;
  gap: 0.8vw;
  padding: 0.8vh 1vw;
  border: 1px solid #f0f0f0;
  border-radius: 0.6vmax;
  font-size: 1vmax;
}

.snap-time {
  flex: 1;
  min-width: 0;
  color: var(--app-text-color-regular);
}

.snap-tag {
  flex-shrink: 0;
  font-size: 0.85vmax;
  padding: 0 0.5vw;
  border-radius: 0.4vmax;
  background: #f0f0f0;
  color: #909399;
}
.snap-tag.changed {
  background: #fff3e6;
  color: #fa8c16;
}
.snap-tag.current {
  background: #e6f4ff;
  color: #1890ff;
}

.snap-btn {
  flex-shrink: 0;
  font-size: 0.95vmax;
  height: auto;
}

/* 快照查看：iframe 固定高度，内容在内部滚动 */
.snap-view {
  min-height: 300px;
}

.snap-frame {
  width: 100%;
  height: 62vh;
  border: 1px solid #f0f0f0;
  border-radius: 0.6vmax;
  background: #fff;
}
</style>
