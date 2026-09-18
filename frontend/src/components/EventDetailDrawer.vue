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
import { Close } from "@element-plus/icons-vue";
import { useEventStore } from "@/stores/event";
import { fetchEventSnapshots, fetchSnapshotRaw } from "@/api/event";
import type { EventSnapshot } from "@/types/event";

const props = defineProps<{
  modelValue: boolean;
  /** 要展示的事件 id；为 null 时不请求 */
  eventId: number | null;
}>();
const emit = defineEmits<{
  (e: "update:modelValue", value: boolean): void;
  (e: "select", id: number): void;
}>();

const eventStore = useEventStore();

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
    // 打开新事件时重置筛选，再拉取相关事件
    relatedDays.value = "";
    relatedCategory.value = "";
    if (d?.competitorId) await eventStore.loadRelatedEvents(d.competitorId, id);
    await loadSnapshots(id);
  } catch {
    visible.value = false; // 失败提示由 request.ts 拦截器统一弹出
  }
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

// 打开时加载；已打开的情况下切换事件也重新加载
watch(
  () => [props.modelValue, props.eventId] as const,
  ([open, id]) => {
    if (open && id != null) loadDetail(id);
  },
);
</script>

<template>
  <el-drawer
    v-model="visible"
    :with-header="false"
    size="min(760px, 94vw)"
    class="event-detail-drawer"
  >
    <div v-loading="eventStore.detailLoading" class="detail-body">
      <template v-if="detail">
        <header class="detail-head">
          <div
            class="detail-logo"
            :style="{ backgroundColor: detail.iconBg, color: detail.iconColor }"
          >
            {{ detail.iconText }}
          </div>
          <div class="detail-head-main">
            <div class="detail-brand-row">
              <span class="detail-brand">{{ detail.brand }}</span>
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

.detail-head {
  display: flex;
  align-items: center;
  gap: 1vw;
  padding-bottom: 1.5vh;
  border-bottom: 1px solid #f0f0f0;
}

.detail-logo {
  width: 4vmax;
  height: 4vmax;
  min-width: 44px;
  min-height: 44px;
  border-radius: 0.6vmax;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1.6vmax;
  font-weight: bold;
  flex-shrink: 0;
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
