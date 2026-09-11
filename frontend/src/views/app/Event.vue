<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useEventStore } from "@/stores/event";
import { useCompetitorStore } from "@/stores/competitor";
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
  Close,
} from "@element-plus/icons-vue";

const eventStore = useEventStore();
const competitorStore = useCompetitorStore();

// 顶部筛选
const keyword = ref("");
const filterCompetitor = ref("all");
const filterType = ref("all");
const filterPriority = ref("all");
function daysAgo(days: number): Date {
  const d = new Date();
  d.setDate(d.getDate() - days);
  return d;
}

// 默认近 7 天（formatDate 是函数声明会被提升，可提前调用），避免出现写死的过期区间
const dateRange = ref<[string, string]>([
  formatDate(daysAgo(6)),
  formatDate(new Date()),
]);
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
  dateRange.value = [formatDate(start), formatDate(end)];
  activeRange.value = key;
}

// 右侧筛选面板
const sideCompetitor = ref("all");
const sideTypes = ref(["feature", "price", "content", "negative", "other"]);
const sidePriorities = ref(["high", "mid", "low"]);
const sideConfidence = ref<[number, number]>([0, 100]);

const page = ref(1);
const pageSize = ref(10);

onMounted(() => {
  eventStore.loadEventList();
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

// 各优先级的真实数量（替换原先写死的计数）
const priorityCounts = computed(() => {
  const counts: Record<string, number> = { high: 0, mid: 0, low: 0 };
  for (const r of records.value) {
    counts[r.priorityType] = (counts[r.priorityType] ?? 0) + 1;
  }
  return counts;
});

/** 顶部关键字/分类 + 右侧竞品/优先级/置信度 + 日期范围，全部即时生效 */
const filteredRecords = computed(() => {
  const k = keyword.value.trim().toLowerCase();
  let list = records.value;

  if (activeCategory.value !== "total") {
    list = list.filter((r) => r.category === activeCategory.value);
  }
  if (sideCompetitor.value !== "all") {
    list = list.filter((r) => String(r.competitorId ?? "") === sideCompetitor.value);
  }
  list = list.filter((r) => sidePriorities.value.includes(r.priorityType));

  const [minConfidence, maxConfidence] = sideConfidence.value;
  list = list.filter(
    (r) => r.aiConfidence >= minConfidence && r.aiConfidence <= maxConfidence,
  );

  if (k) {
    list = list.filter((r) =>
      [r.title, r.desc, r.brand, ...(r.keywords ?? [])]
        .join(" ")
        .toLowerCase()
        .includes(k),
    );
  }

  const [startDate, endDate] = dateRange.value;
  return list.filter((r) => r.date >= startDate && r.date <= endDate);
});

function resetFilters() {
  keyword.value = "";
  filterCompetitor.value = "all";
  filterType.value = "all";
  filterPriority.value = "all";
  activeCategory.value = "total";
  sideCompetitor.value = "all";
  sidePriorities.value = ["high", "mid", "low"];
  sideConfidence.value = [0, 100];
  setQuickRange("7d");
}

// ---- 事件详情抽屉 ----
const detailVisible = ref(false);
const detail = computed(() => eventStore.eventDetail);

async function openDetail(record: EventRecord) {
  detailVisible.value = true; // 先开抽屉再加载，用 loading 遮罩承接等待
  try {
    await eventStore.loadEventDetail(record.id);
  } catch {
    detailVisible.value = false; // 失败提示由 request.ts 拦截器统一弹出
  }
}

/** 把 unified diff 拆行渲染，按行着色 */
const diffLines = computed(() => (detail.value?.diffDetail ?? "").split("\n"));

function diffLineClass(line: string): string {
  if (line.startsWith("+++") || line.startsWith("---")) return "diff-file";
  if (line.startsWith("@@")) return "diff-hunk";
  if (line.startsWith("+")) return "diff-add";
  if (line.startsWith("-")) return "diff-del";
  return "diff-ctx";
}

// 按日期分组
const groups = computed(() => {
  const map = new Map<string, { label: string; items: EventRecord[] }>();
  for (const r of filteredRecords.value) {
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
                    <div class="event-desc">
                      {{ item.title }}，{{ item.desc }}
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
          </div>
        </div>

        <!-- 分页（固定在底部，不随列表滚动） -->
        <div class="pagination-bar">
          <span class="total-text">共 {{ filteredRecords.length }} 条事件</span>
          <el-pagination
            v-model:current-page="page"
            v-model:page-size="pageSize"
            :total="filteredRecords.length"
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
          <el-button type="text" class="reset-btn" @click="resetFilters"
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

    <!-- 事件详情抽屉 -->
    <el-drawer
      v-model="detailVisible"
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
            <el-button link :icon="Close" @click="detailVisible = false" />
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
        </template>
      </div>
    </el-drawer>
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

.event-tag {
  font-size: 1vmax;
  padding: 0 0.5vw;
  border-radius: 0.4vmax;
}

.tag-new {
  background-color: #e6f9f0;
  color: #22c55e;
}
.tag-price {
  background-color: #fff3e6;
  color: #fa8c16;
}
.tag-update {
  background-color: #e6f4ff;
  color: #1890ff;
}
.tag-negative {
  background-color: #fff1f0;
  color: #ff4d4f;
}
.tag-other {
  background-color: #f0f0f0;
  color: #909399;
}

.event-sub {
  font-size: 1vmax;
  color: var(--app-color-gray);
}

.event-desc {
  font-size: 1vmax;
}

.event-keywords {
  display: flex;
  gap: 0.5vw;
}

.keyword {
  font-size: 1vmax;
  padding: 0 0.5vw;
  border-radius: 0.4vmax;
  background: #f4f4f5;
  color: var(--app-color-gray);
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

.priority-tag {
  font-size: 1vmax;
  padding: 0 0.5vw;
  border-radius: 0.4vmax;
}

.priority-tag.high {
  background: #fff1f0;
  color: #ff4d4f;
}
.priority-tag.mid {
  background: #fff3e6;
  color: #fa8c16;
}
.priority-tag.low {
  background: #f0f0f0;
  color: #909399;
}

.detail-btn {
  align-self: flex-end;
}

.event-ago {
  font-size: 1vmax;
  color: var(--app-color-gray);
  text-align: right;
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

/* ===== 事件详情抽屉 ===== */
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
</style>
