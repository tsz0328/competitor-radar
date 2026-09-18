<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { useRoute } from "vue-router";
import { useEventStore } from "@/stores/event";
import { useCompetitorStore } from "@/stores/competitor";
import EventDetailDrawer from "@/components/EventDetailDrawer.vue";
import type { EventRecord } from "@/types/event";
import {
  Search,
  Calendar,
  Collection,
  Promotion,
  PriceTag,
  Document,
  Warning,
  MoreFilled,
  ArrowLeft,
  ArrowRight,
} from "@element-plus/icons-vue";

const eventStore = useEventStore();
const competitorStore = useCompetitorStore();
const route = useRoute();

// 顶部筛选（关键词做 300ms 防抖，避免每次按键都打接口）
const keyword = ref("");
const appliedKeyword = ref("");
let kwTimer: ReturnType<typeof setTimeout> | undefined;
watch(
  keyword,
  (v) => {
    if (kwTimer) clearTimeout(kwTimer);
    kwTimer = setTimeout(() => {
      appliedKeyword.value = v;
    }, 300);
  },
);

// 默认近 7 天；formatDate 是函数声明会被提升，可提前调用
const dateRange = ref<[string, string] | null>(["", ""]);
const activeRange = ref("7d"); // 当前选中的快捷预设：'' | 'today' | '7d' | '30d'

function formatDate(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function setQuickRange(key: string) {
  const end = new Date();
  const start = new Date();
  if (key === "7d") start.setDate(end.getDate() - 6);
  else if (key === "30d") start.setDate(end.getDate() - 29);
  else if (key !== "") return; // 自定义日期由日期选择器直接改 dateRange，这里不动
  dateRange.value = [formatDate(start), formatDate(end)];
  activeRange.value = key;
}

// 初始化为近 7 天
setQuickRange("7d");

// 从工作台趋势图点击某天钻取过来：直接筛选该日
const dateParam = route.query.date;
if (typeof dateParam === "string" && dateParam) {
  dateRange.value = [dateParam, dateParam];
  activeRange.value = "";
}

// 右侧筛选面板（支持从趋势页带 competitorId 跳转过来时预选竞品）
const competitorParam = route.query.competitorId;
const sideCompetitor = ref(
  typeof competitorParam === "string" && competitorParam ? competitorParam : "all",
);
const sideTypes = ref(["feature", "price", "content", "negative", "other"]);
const priorityParam = route.query.priority;
const initialPriorities = typeof priorityParam === "string" ? priorityParam.split(",").filter(Boolean) : null;
const sidePriorities = ref(initialPriorities ?? ["high", "mid", "low"]);
const sideConfidence = ref<[number, number]>([0, 100]);

const page = ref(1);
const pageSize = ref(10);

onMounted(() => {
  competitorStore.loadCompetitors(); // 右侧「竞品」筛选用真实数据
});

const summary = computed(() => eventStore.eventList?.summary);
const records = computed(() => eventStore.eventList?.records ?? []);

// 顶部统计卡片：展示配置（稳定，留前端）+ 数值来自接口 summary
const SUMMARY_CARD_DEFS = [
  { key: "total", label: "全部事件", cls: "chip-total", icon: Collection },
  { key: "feature", label: "功能更新", cls: "chip-feature", icon: Promotion },
  { key: "price", label: "价格变化", cls: "chip-price", icon: PriceTag },
  { key: "content", label: "内容更新", cls: "chip-content", icon: Document },
  { key: "negative", label: "舆论动态", cls: "chip-negative", icon: Warning },
  { key: "other", label: "其他", cls: "chip-other", icon: MoreFilled },
] as const;

// 当前选中的分类筛选（"total" 表示全部）
const activeCategory = ref<"total" | "feature" | "price" | "content" | "negative" | "other">("total");

const summaryCards = computed(() =>
  SUMMARY_CARD_DEFS.map((d) => ({
    ...d,
    value: summary.value?.[d.key] ?? 0,
  }))
);

// 右侧「竞品」下拉：真实竞品，value 用字符串化的 id
const competitorOptions = computed(() =>
  competitorStore.competitors.map((c) => ({ label: c.name, value: String(c.id) })),
);

// 各优先级的真实数量（来自后端分面计数，不被优先级自身筛选清零）
const priorityCounts = computed(() => ({
  high: summary.value?.high ?? 0,
  mid: summary.value?.mid ?? 0,
  low: summary.value?.low ?? 0,
}));

// 拼接后端查询参数：分页 + 全部筛选下推到服务端
const queryParams = computed(() => {
  const p: Record<string, unknown> = {
    limit: pageSize.value,
    offset: (page.value - 1) * pageSize.value,
  };
  if (sideCompetitor.value !== "all") p.competitorId = Number(sideCompetitor.value);
  if (activeCategory.value !== "total") p.category = activeCategory.value;
  if (sidePriorities.value.length) p.priority = sidePriorities.value.join(",");
  if (sideConfidence.value[0] > 0) p.minConfidence = sideConfidence.value[0];
  if (sideConfidence.value[1] < 100) p.maxConfidence = sideConfidence.value[1];
  const k = appliedKeyword.value.trim();
  if (k) p.keyword = k;
  const [s, e] = dateRange.value ?? [];
  if (s) p.startDate = s;
  if (e) p.endDate = e;
  return p;
});

function loadEvents() {
  eventStore.loadEventList(queryParams.value);
}

// 筛选条件（不含分页）变化 → 回到第 1 页并重新拉取
watch(
  () => ({
    competitor: sideCompetitor.value,
    category: activeCategory.value,
    priorities: [...sidePriorities.value],
    conf: [...sideConfidence.value],
    keyword: appliedKeyword.value,
    range: [...(dateRange.value ?? [])],
    rangeKey: activeRange.value,
  }),
  () => {
    page.value = 1;
    loadEvents();
  },
  { immediate: true },
);

// 仅分页变化 → 重新拉取（切页不回第 1 页，换每页条数则回第 1 页）
watch(page, () => loadEvents());
watch(pageSize, () => {
  if (page.value !== 1) {
    page.value = 1; // 会触发上面的 page watch 拉取，无需重复请求
  } else {
    loadEvents();
  }
});

function resetFilters() {
  keyword.value = "";
  appliedKeyword.value = "";
  activeCategory.value = "total";
  sideCompetitor.value = "all";
  sidePriorities.value = ["high", "mid", "low"];
  sideConfidence.value = [0, 100];
  setQuickRange("7d");
}

// ---- 事件详情抽屉：本体是公共组件，这里只负责"打开哪一条" ----
const detailVisible = ref(false);
const detailId = ref<number | null>(null);

function openDetail(record: EventRecord) {
  detailId.value = record.id;
  detailVisible.value = true; // 组件打开后自行加载，等待态由组件承接
}

// 抽屉内"相关事件"跳转：更新 eventId 即可，抽屉自身的 watch 会重新加载详情
function onSelectRelated(id: number) {
  detailId.value = id;
}

// 按日期分组
const groups = computed(() => {
  const map = new Map<string, { label: string; items: EventRecord[] }>();
  for (const r of records.value) {
    if (!map.has(r.date)) {
      map.set(r.date, { label: r.dateLabel, items: [] });
    }
    map.get(r.date)!.items.push(r);
  }
  return [...map.entries()].map(([date, g]) => ({ date, ...g }));
});
</script>

<template>
  <div class="event-page">
    <!-- 顶部筛选栏 -->
    <div class="filter-bar card">
      <el-input
        v-model="keyword"
        class="filter-search"
        placeholder="搜索事件、竞品或关键词..."
        :prefix-icon="Search"
        clearable
      />
      <div class="range-btns">
        <el-button
          v-for="r in [
            { key: 'today', label: '今天' },
            { key: '7d', label: '近 7 天' },
            { key: '30d', label: '近 30 天' },
          ]"
          :key="r.key"
          :type="activeRange === r.key ? 'primary' : 'default'"
          @click="setQuickRange(r.key)"
        >
          {{ r.label }}
        </el-button>
      </div>
      <el-date-picker
        v-model="dateRange"
        class="filter-date"
        type="daterange"
        start-placeholder="开始日期"
        end-placeholder="结束日期"
        value-format="YYYY-MM-DD"
        :prefix-icon="Calendar"
        @change="activeRange = ''"
      />
    </div>

    <!-- 类型统计 -->
    <div class="summary-chips">
      <div
        v-for="c in summaryCards"
        :key="c.key"
        class="summary-chip card"
        :class="[c.cls, { 'is-active': activeCategory === c.key }]"
        @click="activeCategory = c.key"
      >
        <el-icon class="chip-icon"><component :is="c.icon" /></el-icon>
        <div class="chip-text">
          <div class="chip-label">{{ c.label }}</div>
          <div class="chip-value">{{ c.value }}</div>
        </div>
      </div>
    </div>

    <div class="main">
      <!-- 左侧时间线 + 分页 -->
      <div class="timeline-col">
        <div class="timeline" v-loading="eventStore.listLoading">
          <div class="timeline-content">
            <div v-for="g in groups" :key="g.date" class="date-group">
              <div class="date-head">
                <span class="date-text">{{ g.date }}</span>
                <span class="date-label">{{ g.label }}</span>
              </div>
              <div v-for="item in g.items" :key="item.id" class="event-row">
                <div class="event-time">
                  <span>{{ item.time }}</span>
                  <span class="time-dot" :class="item.priorityType"></span>
                </div>
                <div class="event-card card">
                  <div
                    class="event-logo"
                    :style="{
                      backgroundColor: item.iconBg,
                      color: item.iconColor,
                    }"
                  >
                    {{ item.iconText }}
                  </div>
                  <div class="event-body">
                    <div class="event-head">
                      <span class="event-brand">{{ item.brand }}</span>
                      <span class="event-tag" :class="item.tagType">{{
                        item.tag
                      }}</span>
                    </div>
                    <div class="event-sub">{{ item.brandDesc }}</div>
                    <div class="event-title">{{ item.title }}</div>
                    <div class="event-desc">{{ item.desc }}</div>
                    <div v-if="item.aiAnalysis" class="event-ai">
                      <span class="ai-label">AI 分析</span>
                      <span class="ai-text">{{ item.aiAnalysis }}</span>
                    </div>
                    <div class="event-keywords">
                      <span
                        v-for="k in item.keywords"
                        :key="k"
                        class="keyword"
                        >{{ k }}</span
                      >
                    </div>
                  </div>
                  <div class="event-side">
                    <div class="confidence">
                      <span class="side-label">AI 置信度</span>
                      <div class="confidence-bar">
                        <el-progress
                          :percentage="item.aiConfidence"
                          :show-text="false"
                          color="#22c55e"
                        />
                        <span class="confidence-value"
                          >{{ item.aiConfidence }}%</span
                        >
                      </div>
                    </div>
                    <div class="priority">
                      <span class="side-label">优先级</span>
                      <span class="priority-tag" :class="item.priorityType">
                        {{ item.priority }}
                      </span>
                    </div>
                    <el-button
                      class="detail-btn"
                      size="small"
                      @click="openDetail(item)"
                    >
                      查看详情
                    </el-button>
                    <div class="event-ago">{{ item.ago }}</div>
                  </div>
                </div>
              </div>
            </div>
          <div v-if="!eventStore.listLoading && groups.length === 0" class="empty">
            暂无符合条件的事件
          </div>
          </div>
        </div>

        <!-- 分页（固定在底部，不随列表滚动） -->
        <div class="pagination-bar">
          <span class="total-text">共 {{ eventStore.eventList?.total ?? 0 }} 条事件</span>
          <el-pagination
            v-model:current-page="page"
            v-model:page-size="pageSize"
            :total="eventStore.eventList?.total ?? 0"
            :page-sizes="[10, 20, 50]"
            layout="prev, pager, next, sizes"
            :prev-icon="ArrowLeft"
            :next-icon="ArrowRight"
            background
          />
        </div>
      </div>

      <!-- 右侧筛选条件 -->
      <aside class="side-filter card">
        <header class="side-head">
          <span class="side-title">筛选条件</span>
          <el-button link class="reset-btn" @click="resetFilters"
            >重置</el-button
          >
        </header>

        <div class="side-section">
          <div class="side-label">竞品</div>
          <el-select v-model="sideCompetitor" class="side-select">
            <el-option label="全部竞品" value="all" />
            <el-option
              v-for="opt in competitorOptions"
              :key="opt.value"
              :label="opt.label"
              :value="opt.value"
            />
          </el-select>
        </div>

        <div class="side-section">
          <div class="side-label">优先级</div>
          <el-checkbox-group v-model="sidePriorities" class="side-checks">
            <el-checkbox value="high">
              <span class="check-dot high"></span>高<span class="check-count"
                >({{ priorityCounts.high }})</span
              >
            </el-checkbox>
            <el-checkbox value="mid">
              <span class="check-dot mid"></span>中<span class="check-count"
                >({{ priorityCounts.mid }})</span
              >
            </el-checkbox>
            <el-checkbox value="low">
              <span class="check-dot low"></span>低<span class="check-count"
                >({{ priorityCounts.low }})</span
              >
            </el-checkbox>
          </el-checkbox-group>
        </div>

        <div class="side-section">
          <div class="side-label">AI 置信度</div>
          <el-slider v-model="sideConfidence" range :min="0" :max="100" />
        </div>

        <el-button class="apply-btn" type="primary" @click="resetFilters"
          >重置全部筛选</el-button
        >
      </aside>
    </div>

    <!-- 事件详情抽屉（事件流页与 Dashboard 共用同一个组件） -->
    <EventDetailDrawer v-model="detailVisible" :event-id="detailId" @select="onSelectRelated" />
  </div>
</template>

<style scoped>
.event-page {
  height: 100%;
  padding: 2vh 2vw;
  display: flex;
  flex-direction: column;
  gap: 2vh;
  overflow: auto;
}

.card {
  background-color: var(--app-color-white);
  border-radius: 1vmax;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.1);
}

/* 顶部筛选栏 */
.filter-bar {
  display: flex;
  align-items: center;
  gap: 1vw;
  padding: 1vh 1vw;
}

.filter-search {
  flex: 1;
  min-width: 200px;
}

:deep(.el-date-editor.el-range-editor) {
  width: 240px ;
  flex: none ;
}
:deep(.el-date-editor .el-range__icon){
  font-size: 16px;
}
:deep(.el-date-editor .el-range-input){
  width: 40%;
  font-size: 16px;
  line-height: 31px;
}

/* 类型统计 */
.summary-chips {
  display: grid;
  grid-template-columns: repeat(6, 1fr);
  gap: 1vw;
}

.summary-chip {
  display: flex;
  align-items: center;
  gap: 1vw;
  padding: 1vh 1vw;
}

.summary-chip.is-active {
  outline: 2px solid #5b6fff;
  outline-offset: -2px;
}

.chip-icon {
  width: 3vmax;
  height: 3vmax;
  min-width: 28px;
  min-height: 28px;
  border-radius: 0.6vmax;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1.4vmax;
}

.chip-total .chip-icon {
  background: #e6eaff;
  color: #5b6fff;
}
.chip-feature .chip-icon {
  background: #e6f9f0;
  color: #22c55e;
}
.chip-price .chip-icon {
  background: #fff3e6;
  color: #fa8c16;
}
.chip-content .chip-icon {
  background: #e6f4ff;
  color: #1890ff;
}
.chip-negative .chip-icon {
  background: #fff1f0;
  color: #ff4d4f;
}
.chip-other .chip-icon {
  background: #f0f0f0;
  color: #909399;
}

.chip-label {
  font-size: 1vmax;
  color: var(--app-color-gray);
}

.chip-value {
  font-size: 1.4vmax;
  font-weight: bold;
}

/* 主区域 */
.main {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: 3fr 1fr;
  grid-template-rows: minmax(0, 1fr);
  gap: 1.5vw;
}

/* 左侧列：列表滚动 + 分页固定 */
.timeline-col {
  display: flex;
  flex-direction: column;
  gap: 1vh;
  min-height: 0;
}

/* 时间线 */
.timeline {
  flex: 1;
  display: flex;
  min-height: 0;
  background-color: var(--app-color-white);
  border-radius: 1vmax;
  padding: 1vh 1vw;
}
.timeline-content{
  flex: 1;
  display: flex;
  min-height: 0;
  flex-direction: column;
  padding: 1vh 1vw;
  overflow: auto;
}

/* 每个日期分组内独立画一条时间轴，分组之间自然断开、不穿过标题 */
.date-group {
  position: relative;
}

.date-group::before {
  content: "";
  position: absolute;
  left: calc(4.5vw - 11px);
  top: calc(3vh + 4px);
  bottom: 1.5vh;
  width: 2px;
  background: #e6e6e6;
  z-index: 0;
}

.date-head {
  display: flex;
  align-items: baseline;
  gap: 0.5vw;
  margin-bottom: 1vh;
}

.date-text {
  font-size: 1vmax;
  font-weight: bold;
}

.date-label {
  font-size: 1vmax;
  color: var(--app-color-gray);
}

.event-row {
  display: flex;
  gap: 1vw;
  margin-bottom: 1.5vh;
  position: relative;
}

.event-time {
  width: 4.5vw;
  flex-shrink: 0;
  align-self: stretch;
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 0.5vw;
  font-size: 1vmax;
  color: var(--app-color-gray);
  padding-top: 1.5vh;
  position: relative;
}

.time-dot {
  position: absolute;
  right: 6px;
  top: calc(1.5vh + 4px);
  z-index: 1;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #c0c4cc;
}

.time-dot.high {
  background: #ff4d4f;
}
.time-dot.mid {
  background: #fa8c16;
}
.time-dot.low {
  background: #1890ff;
}

.event-card {
  flex: 1;
  display: flex;
  gap: 1vw;
  padding: 1.5vh 1vw;
  align-items: flex-start;
}

.event-logo {
  width: 4vmax;
  height: 4vmax;
  min-width: 36px;
  min-height: 36px;
  border-radius: 0.6vmax;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1.6vmax;
  font-weight: bold;
  flex-shrink: 0;
}

.event-body {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 0.4vh;
  min-width: 0;
}

.event-head {
  display: flex;
  align-items: center;
  gap: 0.8vw;
  position: relative;
  z-index: 1;
  background: var(--app-color-white);
}

.event-brand {
  font-size: 1.1vmax;
  font-weight: bold;
}

.event-sub {
  font-size: 1vmax;
  color: var(--app-color-gray);
}

.event-title {
  font-size: 1.1vmax;
  font-weight: bold;
}

.event-desc {
  font-size: 1vmax;
}

/* AI 如何理解这条变化：与事实摘要视觉区分 */
.event-ai {
  display: flex;
  align-items: baseline;
  gap: 0.6vw;
  margin-top: 0.3vh;
  padding: 0.6vh 0.8vw;
  font-size: 1vmax;
  color: #5b21b6;
  background: #faf7ff;
  border: 1px solid #ece4fb;
  border-radius: 0.6vmax;
}

.ai-label {
  flex-shrink: 0;
  font-size: 0.85vmax;
  color: #8b5cf6;
  border: 1px solid #e0d4fb;
  border-radius: 0.4vmax;
  padding: 0 0.4vw;
}

.ai-text {
  min-width: 0;
}

.event-keywords {
  display: flex;
  gap: 0.5vw;
}

.event-side {
  width: 10vw;
  min-width: 130px;
  display: flex;
  flex-direction: column;
  gap: 0.8vh;
  flex-shrink: 0;
}

.side-label {
  font-size: 1vmax;
  color: var(--app-color-gray);
}

.confidence-bar {
  display: flex;
  align-items: center;
  gap: 0.5vw;
}

.confidence-bar :deep(.el-progress) {
  flex: 1;
}

.confidence-value {
  font-size: 1vmax;
  font-weight: bold;
  color: #22c55e;
}

.priority {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.detail-btn {
  align-self: flex-end;
}

.event-ago {
  font-size: 1vmax;
  color: var(--app-color-gray);
  text-align: right;
}

/* 空状态 */
.empty {
  text-align: center;
  color: var(--app-color-gray);
  padding: 6vh 0;
  font-size: 1.1vmax;
}

/* 分页 */
.pagination-bar {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.total-text {
  font-size: 1vmax;
  color: var(--app-color-gray);
}

/* 右侧筛选 */
.side-filter {
  padding: 1.5vh 1vw;
  display: flex;
  flex-direction: column;
  gap: 1.5vh;
  align-self: start;
}

.side-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.side-title {
  font-size: 1.1vmax;
  font-weight: bold;
}

.reset-btn {
  font-size: 1vmax;
  height: auto;
}

.side-section {
  display: flex;
  flex-direction: column;
  gap: 0.8vh;
}

.side-select {
  width: 100%;
}

.side-checks {
  display: flex;
  flex-direction: column;
  gap: 0.4vh;
}

.side-checks :deep(.el-checkbox) {
  height: auto;
}

.check-dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  margin-right: 4px;
}

.check-dot.high {
  background: #ff4d4f;
}
.check-dot.mid {
  background: #fa8c16;
}
.check-dot.low {
  background: #22c55e;
}

.check-count {
  margin-left: 4px;
  color: var(--app-color-gray);
  font-size: 1vmax;
}

.range-btns {
  display: flex;
  gap: 0.5vw;
}

.range-btns .el-button {
  flex: 1;
  margin-left: 0;
}

.apply-btn {
  width: 100%;
}

</style>
