<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useEventStore } from "@/stores/event";
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

// 顶部筛选
const keyword = ref("");
const filterCompetitor = ref("all");
const filterType = ref("all");
const filterPriority = ref("all");
const dateRange = ref<[string, string]>(["2026-06-18", "2026-06-25"]);
const activeRange = ref(""); // 当前选中的快捷预设：'' | 'today' | '7d' | '30d'

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
});

const summary = computed(() => eventStore.eventList?.summary);
const records = computed(() => eventStore.eventList?.records ?? []);

// 顶部统计卡片：展示配置（稳定，留前端）+ 数值来自接口 summary
const SUMMARY_CARD_DEFS = [
  { key: "total", label: "全部事件", cls: "chip-total", icon: Collection },
  { key: "feature", label: "功能更新", cls: "chip-feature", icon: Promotion },
  { key: "price", label: "价格变化", cls: "chip-price", icon: PriceTag },
  { key: "content", label: "内容更新", cls: "chip-content", icon: Document },
  { key: "negative", label: "负面舆情", cls: "chip-negative", icon: Warning },
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

// 按选中分类筛选事件（total = 全部）
const filteredRecords = computed(() =>
  activeCategory.value === "total"
    ? records.value
    : records.value.filter((r) => r.category === activeCategory.value)
);

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
                    <el-button class="detail-btn" size="small"
                      >查看详情</el-button
                    >
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
          <el-button type="text" class="reset-btn">重置</el-button>
        </header>

        <div class="side-section">
          <div class="side-label">竞品</div>
          <el-select v-model="sideCompetitor" class="side-select">
            <el-option label="全部竞品" value="all" />
            <el-option label="OpenAI" value="openai" />
            <el-option label="Claude" value="claude" />
            <el-option label="Midjourney" value="midjourney" />
            <el-option label="Google Gemini" value="gemini" />
            <el-option label="Perplexity" value="perplexity" />
          </el-select>
        </div>

        <div class="side-section">
          <div class="side-label">优先级</div>
          <el-checkbox-group v-model="sidePriorities" class="side-checks">
            <el-checkbox value="high">
              <span class="check-dot high"></span>高<span class="check-count"
                >(16)</span
              >
            </el-checkbox>
            <el-checkbox value="mid">
              <span class="check-dot mid"></span>中<span class="check-count"
                >(20)</span
              >
            </el-checkbox>
            <el-checkbox value="low">
              <span class="check-dot low"></span>低<span class="check-count"
                >(6)</span
              >
            </el-checkbox>
          </el-checkbox-group>
        </div>

        <div class="side-section">
          <div class="side-label">AI 置信度</div>
          <el-slider v-model="sideConfidence" range :min="0" :max="100" />
        </div>

        <el-button class="apply-btn" type="primary">应用筛选 (5)</el-button>
      </aside>
    </div>
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
</style>
