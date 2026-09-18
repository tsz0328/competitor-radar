<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import { useCompetitorStore } from "@/stores/competitor";
import {
  fetchCompetitorTrend,
  fetchTrend,
  fetchTrendCompare,
  fetchTrendInsight,
} from "@/api/trend";
import { fetchEventList } from "@/api/event";
import type { CompetitorSeries, TrendInsight, TrendPoint } from "@/types/trend";
import type { EventRecord, EventSummary } from "@/types/event";
import TrendChart from "@/components/Charts/TrendChart.vue";
import CompetitorCompareChart from "@/components/Charts/CompetitorCompareChart.vue";
import EventDetailDrawer from "@/components/EventDetailDrawer.vue";
import { Refresh } from "@element-plus/icons-vue";

const router = useRouter();
const competitorStore = useCompetitorStore();

// 选中单个竞品时看它的深度趋势与 AI 判断；选"全部"则看多竞品对比
const selectedId = ref<number | "all">("all");
const range = ref("30");

const seriesLoading = ref(false);
const series = ref<TrendPoint[]>([]);
const compareSeries = ref<CompetitorSeries[]>([]);
const insightLoading = ref(false);
const insight = ref<TrendInsight | null>(null);
const overviewSummary = ref<EventSummary | null>(null);
const relatedEvents = ref<EventRecord[]>([]);

const RANGE_OPTIONS = [
  { label: "近 7 天", value: "7" },
  { label: "近 30 天", value: "30" },
  { label: "近 90 天", value: "90" },
];

const isAll = computed(() => selectedId.value === "all");
const days = computed(() => Number(range.value) as 7 | 30 | 90);

const competitorOptions = computed(() =>
  competitorStore.competitors.map((c) => ({ label: c.name, value: c.id })),
);

// 趋势概览：变化总量 + 各类型数量（来自事件统计，口径与情报中心一致）
const OVERVIEW_DEFS = [
  { key: "total", label: "变化总量" },
  { key: "feature", label: "功能更新" },
  { key: "price", label: "价格变化" },
  { key: "content", label: "内容更新" },
  { key: "negative", label: "舆论动态" },
  { key: "other", label: "其他" },
] as const;

const overviewCards = computed(() =>
  OVERVIEW_DEFS.map((def) => ({
    ...def,
    value: overviewSummary.value?.[def.key] ?? 0,
  })),
);

// 单竞品的类型分布（用条形比例表达，避免再引入一个图表）
const distItems = computed(() => {
  const summary = overviewSummary.value;
  if (!summary) return [];
  const items = [
    { key: "feature", label: "功能更新", value: summary.feature },
    { key: "price", label: "价格变化", value: summary.price },
    { key: "content", label: "内容更新", value: summary.content },
    { key: "negative", label: "舆论动态", value: summary.negative },
    { key: "other", label: "其他", value: summary.other },
  ].filter((item) => item.value > 0);
  const max = Math.max(1, ...items.map((item) => item.value));
  return items.map((item) => ({
    ...item,
    percent: Math.round((item.value / max) * 100),
  }));
});

async function loadSeries() {
  seriesLoading.value = true;
  try {
    series.value = isAll.value
      ? await fetchTrend(days.value)
      : await fetchCompetitorTrend(selectedId.value as number, days.value);
  } catch {
    series.value = []; // 错误提示由 request.ts 统一弹出
  } finally {
    seriesLoading.value = false;
  }
}

async function loadCompare() {
  if (!isAll.value) {
    compareSeries.value = [];
    return;
  }
  try {
    compareSeries.value = await fetchTrendCompare(days.value);
  } catch {
    compareSeries.value = [];
  }
}

async function loadInsight() {
  // 洞察是按竞品维度给出的，看"全部"时没有单一结论
  if (isAll.value) {
    insight.value = null;
    return;
  }
  insightLoading.value = true;
  try {
    insight.value = await fetchTrendInsight(selectedId.value as number, days.value);
  } catch {
    insight.value = null;
  } finally {
    insightLoading.value = false;
  }
}

async function loadOverview() {
  try {
    const params: Record<string, unknown> = { days: days.value, limit: 1 };
    if (!isAll.value) params.competitorId = selectedId.value;
    const data = await fetchEventList(params);
    overviewSummary.value = data.summary;
  } catch {
    overviewSummary.value = null;
  }
}

async function loadRelated() {
  if (isAll.value) {
    relatedEvents.value = [];
    return;
  }
  try {
    const data = await fetchEventList({
      competitorId: selectedId.value,
      days: days.value,
      limit: 5,
    });
    relatedEvents.value = data.records ?? [];
  } catch {
    relatedEvents.value = [];
  }
}

async function reloadAll() {
  await Promise.all([
    loadSeries(),
    loadCompare(),
    loadInsight(),
    loadOverview(),
    loadRelated(),
  ]);
}

async function refresh() {
  await reloadAll();
  ElMessage.success("趋势数据已刷新");
}

function goToEvents() {
  if (isAll.value) {
    router.push({ name: "Event" });
    return;
  }
  router.push({ name: "Event", query: { competitorId: String(selectedId.value) } });
}

// ---- 情报详情抽屉：从趋势钻到具体情报 ----
const detailVisible = ref(false);
const detailId = ref<number | null>(null);

function openDetail(id: number) {
  detailId.value = id;
  detailVisible.value = true;
}

function onSelectRelated(id: number) {
  detailId.value = id;
}

onMounted(async () => {
  await competitorStore.loadCompetitors();
  await reloadAll();
});

watch([selectedId, range], () => {
  reloadAll();
});
</script>

<template>
  <div class="trend-page">
    <header class="trend-header card">
      <div class="header-left">
        <div class="title">趋势分析</div>
        <div class="subtitle">长期来看，竞争对手正在往哪里走</div>
      </div>
      <div class="header-right">
        <el-select v-model="selectedId" class="comp-select">
          <el-option label="全部竞品" value="all" />
          <el-option
            v-for="opt in competitorOptions"
            :key="opt.value"
            :label="opt.label"
            :value="opt.value"
          />
        </el-select>
        <el-radio-group v-model="range">
          <el-radio-button
            v-for="r in RANGE_OPTIONS"
            :key="r.value"
            :value="r.value"
            >{{ r.label }}</el-radio-button
          >
        </el-radio-group>
        <el-button :icon="Refresh" @click="refresh">刷新</el-button>
      </div>
    </header>

    <!-- 趋势概览 -->
    <section class="overview-cards">
      <div
        v-for="c in overviewCards"
        :key="c.key"
        class="ov-card card"
        :class="`ov-${c.key}`"
      >
        <div class="ov-value">{{ c.value }}</div>
        <div class="ov-label">{{ c.label }}</div>
      </div>
    </section>

    <!-- 主图：全部竞品 → 多竞品对比；单个竞品 → 类型趋势 -->
    <section class="chart-card card">
      <header class="card-head">
        <div class="card-title">{{ isAll ? "竞品变化对比" : "变化趋势" }}</div>
        <div class="card-hint">
          {{
            isAll
              ? "各竞品每日变化总数，看谁在持续活跃"
              : "按事件类型统计的每日数量"
          }}
        </div>
      </header>
      <div class="chart-body" v-loading="seriesLoading">
        <competitor-compare-chart
          v-if="isAll"
          :data="compareSeries"
          height="320px"
        />
        <trend-chart v-else :data="series" height="320px" />
      </div>
    </section>

    <div class="lower">
      <!-- 全部竞品：变化类型趋势 -->
      <template v-if="isAll">
        <section class="chart-card card">
          <header class="card-head">
            <div class="card-title">变化类型趋势</div>
            <div class="card-hint">全部竞品汇总</div>
          </header>
          <div class="chart-body" v-loading="seriesLoading">
            <trend-chart :data="series" height="240px" />
          </div>
        </section>
        <section class="hint-card card">
          <el-empty
            description="选择一个具体竞品，查看 AI 趋势判断与类型分布"
            :image-size="70"
          />
        </section>
      </template>

      <!-- 单个竞品：AI 趋势判断 + 类型分布 -->
      <template v-else>
        <section class="insight-card card" v-loading="insightLoading">
          <template v-if="insight">
            <header class="insight-head">
              <div class="insight-brand">
                <span class="brand-name">{{ insight.competitorName }}</span>
                <span class="direction-tag" :class="insight.direction">{{
                  insight.directionLabel
                }}</span>
              </div>
              <div class="insight-meta">
                近 {{ insight.periodDays }} 天 · 生成于 {{ insight.generatedAt }}
              </div>
            </header>

            <p class="insight-summary">{{ insight.summary }}</p>

            <div class="insight-stats">
              <div class="stat">
                <span class="stat-value">{{ insight.eventCount }}</span>
                <span class="stat-label">变化事件</span>
              </div>
              <div class="stat">
                <span class="stat-value">{{ insight.highImpactCount }}</span>
                <span class="stat-label">高影响</span>
              </div>
              <div class="stat">
                <span class="stat-value">{{ insight.coverageDays }}</span>
                <span class="stat-label">有变化天数</span>
              </div>
            </div>

            <ul v-if="insight.highlights.length" class="insight-highlights">
              <li v-for="(item, index) in insight.highlights" :key="index">
                {{ item }}
              </li>
            </ul>
          </template>
          <el-empty
            v-else-if="!insightLoading"
            description="暂无趋势判断"
            :image-size="70"
          />
        </section>

        <section class="dist-card card">
          <header class="card-head">
            <div class="card-title">变化类型分布</div>
            <div class="card-hint">近 {{ days }} 天</div>
          </header>
          <div class="dist-list">
            <div v-for="d in distItems" :key="d.key" class="dist-item">
              <span class="dist-label">{{ d.label }}</span>
              <div class="dist-bar">
                <i :style="{ width: `${d.percent}%` }" />
              </div>
              <span class="dist-value">{{ d.value }}</span>
            </div>
            <div v-if="!distItems.length" class="dist-empty">
              该周期内没有检测到变化
            </div>
          </div>
        </section>
      </template>
    </div>

    <!-- 单个竞品：相关重要情报（可点开证据） -->
    <section v-if="!isAll" class="related card">
      <header class="card-head">
        <div class="card-title">相关重要情报</div>
        <el-button class="card-button" link @click="goToEvents"
          >在情报中心查看</el-button
        >
      </header>
      <ul class="related-list">
        <li
          v-for="e in relatedEvents"
          :key="e.id"
          class="related-item"
          @click="openDetail(e.id)"
        >
          <span class="event-tag" :class="e.tagType">{{ e.tag }}</span>
          <span class="related-title">{{ e.title }}</span>
          <span class="related-time">{{ e.ago }}</span>
        </li>
        <li v-if="!relatedEvents.length" class="related-empty">
          该周期内没有相关情报
        </li>
      </ul>
    </section>

    <EventDetailDrawer
      v-model="detailVisible"
      :event-id="detailId"
      @select="onSelectRelated"
    />
  </div>
</template>

<style scoped>
.trend-page {
  height: 100%;
  overflow-y: auto;
  padding: 2vh 2vw;
  display: flex;
  flex-direction: column;
  gap: 2vh;
}

.card {
  background-color: var(--app-color-white);
  border-radius: 1vmax;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.1);
}

.trend-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1vw;
  padding: 1.5vh 1vw;
  flex-wrap: wrap;
}

.title {
  font-size: 1.5vmax;
  font-weight: bold;
}

.subtitle {
  font-size: 1vmax;
  color: var(--app-color-gray);
}

.header-right {
  display: flex;
  align-items: center;
  gap: 0.8vw;
}

.comp-select {
  width: 12vw;
  min-width: 140px;
}

/* 趋势概览 */
.overview-cards {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 1vw;
}

.ov-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 0.4vh;
  padding: 1.4vh 0.6vw;
}

.ov-value {
  font-size: 1.6vmax;
  font-weight: bold;
}

.ov-label {
  font-size: 0.95vmax;
  color: var(--app-color-gray);
}

.ov-total .ov-value {
  color: var(--app-color-blue);
}

.card-head {
  display: flex;
  align-items: baseline;
  gap: 0.8vw;
  padding: 1.5vh 1vw 0;
}

.card-title {
  font-size: 1.2vmax;
  font-weight: bold;
}

.card-hint {
  font-size: 0.9vmax;
  color: var(--app-color-gray);
}

.card-button {
  margin-left: auto;
  font-size: 1vmax;
  height: auto;
}

.chart-card {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.chart-body {
  padding: 1vh 1vw 1.5vh;
}

/* 下部：单竞品洞察 + 类型分布 / 全部竞品提示 */
.lower {
  display: grid;
  grid-template-columns: minmax(0, 3fr) minmax(0, 2fr);
  gap: 2vw;
}

.insight-card {
  padding: 1.5vh 1vw;
  display: flex;
  flex-direction: column;
  gap: 1.2vh;
  min-height: 120px;
  min-width: 0;
}

.hint-card {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 200px;
}

.insight-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 1vw;
}

.insight-brand {
  display: flex;
  align-items: center;
  gap: 0.6vw;
}

.brand-name {
  font-size: 1.2vmax;
  font-weight: bold;
}

.direction-tag {
  font-size: 1vmax;
  padding: 0 0.6vw;
  border-radius: 100vmax;
}
.direction-tag.rising {
  background: #e8f8ee;
  color: #12805a;
}
.direction-tag.stable {
  background: #f0f0f0;
  color: #909399;
}
.direction-tag.declining {
  background: #fff3e6;
  color: #fa8c16;
}

.insight-meta {
  font-size: 0.9vmax;
  color: var(--app-color-gray);
}

.insight-summary {
  margin: 0;
  font-size: 1.05vmax;
  line-height: 1.75;
}

.insight-stats {
  display: flex;
  gap: 3vw;
}

.stat {
  display: flex;
  flex-direction: column;
}

.stat-value {
  font-size: 1.5vmax;
  font-weight: bold;
}

.stat-label {
  font-size: 0.9vmax;
  color: var(--app-color-gray);
}

.insight-highlights {
  margin: 0;
  padding-left: 1.2vw;
  display: flex;
  flex-direction: column;
  gap: 0.4vh;
  font-size: 1vmax;
  color: var(--app-text-color-regular);
}

/* 类型分布 */
.dist-card {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.dist-list {
  display: flex;
  flex-direction: column;
  gap: 1.2vh;
  padding: 1.5vh 1vw;
}

.dist-item {
  display: flex;
  align-items: center;
  gap: 0.8vw;
  font-size: 1vmax;
}

.dist-label {
  width: 6vw;
  min-width: 64px;
  flex-shrink: 0;
  color: var(--app-color-gray);
}

.dist-bar {
  flex: 1;
  min-width: 0;
  height: 10px;
  border-radius: 100vmax;
  background: var(--app-color-blue-light-5);
  overflow: hidden;
}
.dist-bar i {
  display: block;
  height: 100%;
  border-radius: 100vmax;
  background: linear-gradient(
    90deg,
    var(--app-color-blue-light-2),
    var(--app-color-purple)
  );
}

.dist-value {
  width: 2.5vw;
  min-width: 28px;
  text-align: right;
  flex-shrink: 0;
  font-weight: bold;
}

.dist-empty {
  font-size: 1vmax;
  color: var(--app-color-gray);
  text-align: center;
  padding: 3vh 0;
}

/* 相关重要情报 */
.related {
  display: flex;
  flex-direction: column;
}

.related-list {
  list-style: none;
  margin: 0;
  padding: 1vh 1vw 1.5vh;
  display: flex;
  flex-direction: column;
  gap: 0.8vh;
}

.related-item {
  display: flex;
  align-items: center;
  gap: 0.8vw;
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
  flex: 1;
  min-width: 0;
  font-size: 1vmax;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.related-time {
  flex-shrink: 0;
  font-size: 0.9vmax;
  color: var(--app-color-gray);
}

.related-empty {
  font-size: 1vmax;
  color: var(--app-color-gray);
  text-align: center;
  padding: 3vh 0;
}

@media (max-width: 1100px) {
  .overview-cards {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
  .lower {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
