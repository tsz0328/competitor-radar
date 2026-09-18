<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { useAuthStore } from "@/stores/auth";
import { useEventStore } from "@/stores/event";
import { useCompetitorStore } from "@/stores/competitor";
import EventDetailDrawer from "@/components/EventDetailDrawer.vue";
import CompetitorLogo from "@/components/CompetitorLogo.vue";
import InfoTrendChart from "@/components/Charts/InfoTrendChart.vue";
import { fetchDailyTrend } from "@/api/trend";
import { fetchEventList } from "@/api/event";
import type { DailyCount } from "@/types/trend";
import { Monitor, List, Warning, DataLine } from "@element-plus/icons-vue";

const router = useRouter();
const eventStore = useEventStore();
const competitorStore = useCompetitorStore();
const authStore = useAuthStore();

// 近 30 天情报变化趋势（导航型图表：点某天钻取到情报中心）
const dailyTrend = ref<DailyCount[]>([]);
const trendDist = ref<
  { key: string; label: string; value: number; percent: number }[]
>([]);

async function loadDailyTrend() {
  try {
    dailyTrend.value = await fetchDailyTrend(30);
  } catch {
    dailyTrend.value = [];
  }
}

// 近 30 天情报类型分布（小条形，辅助理解趋势图，不做成图表中心）
async function loadTrendDist() {
  try {
    const data = await fetchEventList({ days: 30, limit: 1 });
    const summary = data.summary;
    const items = [
      { key: "feature", label: "功能更新", value: summary.feature },
      { key: "price", label: "价格变化", value: summary.price },
      { key: "content", label: "内容更新", value: summary.content },
      { key: "negative", label: "舆论动态", value: summary.negative },
      { key: "other", label: "其他", value: summary.other },
    ].filter((item) => item.value > 0);
    const max = Math.max(1, ...items.map((item) => item.value));
    trendDist.value = items.map((item) => ({
      ...item,
      percent: Math.round((item.value / max) * 100),
    }));
  } catch {
    trendDist.value = [];
  }
}

// 点击趋势图某天 → 去情报中心并筛选该日
function onSelectTrendDate(dateIso: string) {
  router.push({ name: "Event", query: { date: dateIso } });
}

// 工作台只关心「今天」：各模块各自加载，互不阻塞（卡片分别显示加载态）
const trendLoading = ref(false);

onMounted(async () => {
  await Promise.allSettled([
    eventStore.loadEventList({ days: 1, limit: 200 }),
    competitorStore.loadCompetitors(),
    eventStore.loadDailyInsight(1),
    (async () => {
      trendLoading.value = true;
      try {
        await Promise.allSettled([loadDailyTrend(), loadTrendDist()]);
      } finally {
        trendLoading.value = false;
      }
    })(),
  ]);
});

function goTo(name: string, query?: Record<string, string>) {
  router.push({ name, query });
}

const todayRecords = computed(() => eventStore.eventList?.records ?? []);
const todaySummary = computed(() => eventStore.eventList?.summary);
const todayTotal = computed(() => todaySummary.value?.total ?? 0);
const todayHigh = computed(() => todaySummary.value?.high ?? 0);

const displayName = computed(() => authStore.user?.name || "用户");
const greeting = computed(() => {
  const hour = new Date().getHours();
  if (hour < 6) return "夜深了";
  if (hour < 12) return "早上好";
  if (hour < 18) return "下午好";
  return "晚上好";
});
const todayText = new Intl.DateTimeFormat("zh-CN", {
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  weekday: "long",
}).format(new Date());

const monitorPageCount = computed(() =>
  competitorStore.competitors.reduce(
    (total, item) => total + (item.sources?.length ?? 0),
    0,
  ),
);

// 今日有变化的竞品数（按今日事件去重竞品）
const activeCompetitorCount = computed(
  () => new Set(todayRecords.value.map((r) => r.competitorId)).size,
);

// 四个指标回答「今天系统运行得怎么样」，不做深入分析
const statCards = computed(() => [
  {
    key: "competitors",
    title: "监控竞品",
    value: competitorStore.competitors.length,
    desc: `共 ${monitorPageCount.value} 个监控页面`,
    icon: Monitor,
    cls: "icon-blue",
    route: "Competitor",
    query: undefined,
  },
  {
    key: "today",
    title: "今日情报",
    value: todayTotal.value,
    desc: "过去 24 小时",
    icon: List,
    cls: "icon-purple",
    route: "Event",
    query: undefined,
  },
  {
    key: "focus",
    title: "重点变化",
    value: todayHigh.value,
    desc: "高优先级",
    icon: Warning,
    cls: "icon-orange",
    route: "Event",
    query: { priority: "high" },
  },
  {
    key: "active",
    title: "活跃竞品",
    value: activeCompetitorCount.value,
    desc: "今日有变化",
    icon: DataLine,
    cls: "icon-green",
    route: "Event",
    query: undefined,
  },
]);

// 今日重点情报：高/中优先级，优先级优先、其次时间倒序，最多 5 条
const focusEvents = computed(() => {
  const order: Record<string, number> = { high: 0, mid: 1, low: 2 };
  return [...todayRecords.value]
    .filter((r) => r.priorityType === "high" || r.priorityType === "mid")
    .sort(
      (a, b) =>
        (order[a.priorityType] ?? 3) - (order[b.priorityType] ?? 3) ||
        b.date.localeCompare(a.date) ||
        b.time.localeCompare(a.time),
    )
    .slice(0, 5);
});

// 竞品动态：每个竞品今日的变化条数，多的在前
const competitorDynamics = computed(() => {
  const countMap = new Map<number, number>();
  for (const record of todayRecords.value) {
    if (record.competitorId == null) continue;
    countMap.set(record.competitorId, (countMap.get(record.competitorId) ?? 0) + 1);
  }
  return competitorStore.competitors
    .map((item) => ({
      id: item.id,
      name: item.name,
      domain: item.domain,
      logoUrl: item.logoUrl,
      todayCount: countMap.get(item.id) ?? 0,
    }))
    .sort((a, b) => b.todayCount - a.todayCount || a.name.localeCompare(b.name));
});

// 情报中心入口：今日各分类条数（用于「往下钻」的语境）
const categoryChips = computed(() => {
  const summary = todaySummary.value;
  if (!summary) return [];
  return [
    { key: "feature", label: "功能更新", value: summary.feature },
    { key: "price", label: "价格变化", value: summary.price },
    { key: "content", label: "内容更新", value: summary.content },
    { key: "negative", label: "负面舆情", value: summary.negative },
    { key: "other", label: "其他", value: summary.other },
  ].filter((item) => item.value > 0);
});

const insight = computed(() => eventStore.dailyInsight);

// 详情抽屉（与情报中心共用同一个组件）
const detailVisible = ref(false);
const detailId = ref<number | null>(null);

function openDetail(id: number) {
  detailId.value = id;
  detailVisible.value = true;
}

function onSelectRelated(id: number) {
  detailId.value = id;
}
</script>
<template>
  <div class="dashboard">
    <!-- 头部：问候 + 今日概览 -->
    <header class="header">
      <div class="header-left">
        <div class="title">{{ greeting }}，{{ displayName }}</div>
        <div class="subtitle">今天是 {{ todayText }}</div>
      </div>
      <div class="header-overview">
        过去 24 小时，系统发现
        <b>{{ todayTotal }}</b> 条新情报，其中
        <b class="em">{{ todayHigh }}</b> 条值得重点关注
      </div>
    </header>

    <div
      v-if="!competitorStore.loading && competitorStore.competitors.length === 0"
      class="onboarding-hint"
    >
      <span>添加第一个竞品后，这里会自动汇总今日的重点变化。</span>
      <el-button link type="primary" @click="goTo('Competitor')">添加竞品</el-button>
    </div>

    <!-- 指标卡：今天系统运行得怎么样 -->
    <section class="stat-cards">
      <div
        v-for="card in statCards"
        :key="card.key"
        class="stat-card card"
        @click="goTo(card.route, card.query)"
      >
        <div class="stat-card-content">
          <div class="stat-card-title">{{ card.title }}</div>
          <div class="stat-card-value">{{ card.value }}</div>
          <div class="stat-card-desc">{{ card.desc }}</div>
        </div>
        <div class="stat-card-icon" :class="card.cls">
          <el-icon>
            <component :is="card.icon" />
          </el-icon>
        </div>
      </div>
    </section>

    <!-- 趋势导航图 + AI 今日洞察 -->
    <section class="overview-row">
      <div class="card trend-card">
        <header class="card-head">
          <div class="card-title">近 30 天情报变化趋势</div>
          <div class="card-hint">点击某一天，查看当天情报</div>
        </header>
        <div class="trend-body" v-loading="trendLoading">
          <InfoTrendChart
            :data="dailyTrend"
            height="220px"
            @select="onSelectTrendDate"
          />
          <div v-if="trendDist.length" class="dist-strip">
            <div v-for="d in trendDist" :key="d.key" class="dist-mini">
              <span class="dist-mini-label">{{ d.label }}</span>
              <div class="dist-mini-bar">
                <i :style="{ width: `${d.percent}%` }" />
              </div>
              <span class="dist-mini-value">{{ d.value }}</span>
            </div>
          </div>
        </div>
      </div>

      <div class="card insight">
        <header class="card-head">
          <div class="card-title">AI 今日洞察</div>
          <span v-if="insight && !insight.fromLlm" class="insight-badge">规则</span>
        </header>
        <div class="insight-body" v-loading="eventStore.dailyInsightLoading">
          <template v-if="insight">
            <p class="insight-summary">{{ insight.summary }}</p>
            <ul v-if="insight.highlights.length" class="insight-points">
              <li v-for="(point, index) in insight.highlights" :key="index">
                {{ point }}
              </li>
            </ul>
            <div class="insight-foot">
              <span class="insight-scope">
                {{ insight.periodText }} · 涉及 {{ insight.competitorCount }} 个竞品
              </span>
              <el-button class="card-button" link @click="goTo('Event')"
                >查看相关情报</el-button
              >
            </div>
          </template>
          <div v-else-if="!eventStore.dailyInsightLoading" class="empty-hint">
            暂无洞察内容
          </div>
        </div>
      </div>
    </section>

    <!-- 今日重要情报 -->
    <section class="card focus-main">
      <header class="card-head">
        <div class="card-title">今日重要情报</div>
        <el-button
          class="card-button"
          link
          @click="goTo('Event', { priority: 'high,mid' })"
          >查看更多</el-button
        >
      </header>
      <div class="focus-list" v-loading="eventStore.listLoading">
        <div
          v-for="event in focusEvents"
          :key="event.id"
          class="focus-item"
          @click="openDetail(event.id)"
        >
          <CompetitorLogo
            class="focus-logo"
            :name="event.brand"
            :domain="event.domain"
            :src="event.logoUrl"
            :size="44"
          />
          <div class="focus-body">
            <div class="focus-title-row">
              <div class="focus-title">{{ event.title }}</div>
              <span class="event-tag" :class="event.tagType">{{ event.tag }}</span>
              <span class="focus-ago">{{ event.ago }}</span>
            </div>
            <div class="focus-summary">{{ event.summary || event.desc }}</div>
          </div>
        </div>
        <div
          v-if="!focusEvents.length && !eventStore.listLoading"
          class="empty-hint"
        >
          今天暂无需要重点关注的变化
        </div>
      </div>
    </section>

    <!-- 竞品动态：最近哪个竞品比较活跃 -->
    <section class="card dynamics">
      <header class="card-head">
        <div class="card-title">竞品动态</div>
        <el-button class="card-button" link @click="goTo('Competitor')"
          >查看全部</el-button
        >
      </header>
      <div class="dynamics-list" v-loading="competitorStore.loading">
        <div
          v-for="item in competitorDynamics"
          :key="item.id"
          class="dyn-item"
        >
          <CompetitorLogo
            class="dyn-logo"
            :name="item.name"
            :domain="item.domain"
            :src="item.logoUrl"
            :size="36"
          />
          <span class="dyn-name">{{ item.name }}</span>
          <span class="dyn-count">今日 {{ item.todayCount }} 条变化</span>
          <span class="dyn-status" :class="{ active: item.todayCount > 0 }">
            <span class="dyn-dot" />{{ item.todayCount > 0 ? "活跃" : "无变化" }}
          </span>
        </div>
        <div
          v-if="!competitorDynamics.length && !competitorStore.loading"
          class="empty-hint"
        >
          还没有竞品，先添加一个吧
        </div>
      </div>
    </section>

    <!-- 情报中心入口：想看具体发生了什么，往下钻 -->
    <section class="card center-entry">
      <div class="entry-left">
        <div class="entry-title">情报中心</div>
        <div class="entry-desc">
          今日已收录 {{ todayTotal }} 条情报<template v-if="categoryChips.length"
            >：</template
          >
          <span v-for="chip in categoryChips" :key="chip.key" class="entry-chip">
            {{ chip.label }} {{ chip.value }}
          </span>
        </div>
      </div>
      <el-button class="entry-button" type="primary" @click="goTo('Event')">
        查看全部情报
      </el-button>
    </section>

    <!-- 情报详情抽屉（与情报中心共用同一个组件） -->
    <EventDetailDrawer
      v-model="detailVisible"
      :event-id="detailId"
      @select="onSelectRelated"
    />
  </div>
</template>
<style scoped>
.dashboard {
  height: 100%;
  overflow-y: auto;
  padding: 2vh 2vw;
  display: flex;
  flex-direction: column;
  gap: 2vh;
}

.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 2vw;
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

.header-overview {
  font-size: 1vmax;
  color: var(--app-text-color-regular);
  white-space: nowrap;
}
.header-overview b {
  font-size: 1.2vmax;
  color: var(--app-color-blue);
}
.header-overview b.em {
  color: var(--app-color-orange);
}

.onboarding-hint {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1vw;
  padding: 1vh 1vw;
  border-radius: 1vmax;
  background: var(--app-color-blue-light-5);
  color: var(--app-text-color-regular);
}
.onboarding-hint .el-button {
  font-size: 1vmax;
  height: auto;
  white-space: nowrap;
}

.stat-cards {
  flex-shrink: 0;
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 3vw;
}

.card {
  background-color: var(--app-color-white);
  border-radius: 1vmax;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.1);
}

.stat-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1vh 1vw;
  cursor: pointer;
  transition: box-shadow 0.2s ease, transform 0.2s ease;
}
.stat-card:hover {
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.14);
  transform: translateY(-1px);
}

.stat-card-content {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.stat-card-title {
  font-size: 1.2vmax;
  font-weight: bold;
}

.stat-card-value {
  font-size: 1.5vmax;
  font-weight: bold;
}

.stat-card-desc {
  font-size: 1vmax;
  color: var(--app-color-gray);
}

.stat-card-icon {
  width: 4vmax;
  height: 4vmax;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 2vmax;
  flex-shrink: 0;
}

.icon-blue {
  background-color: var(--app-color-blue-light-4);
  color: var(--app-color-blue);
}

.icon-purple {
  background-color: var(--app-color-purple-light-4);
  color: var(--app-color-purple);
}

.icon-green {
  background-color: var(--app-color-green-light-4);
  color: var(--app-color-green);
}

.icon-orange {
  background-color: var(--app-color-orange-light-4);
  color: var(--app-color-orange);
}

.card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1vh 1vw;
  font-size: 1.2vmax;
  flex-shrink: 0;
}

.card-title {
  font-weight: bold;
}

.card-button {
  font-size: 1vmax;
  height: auto;
}

/* ============ 趋势导航图 / AI 今日洞察 ============ */
.overview-row {
  display: grid;
  grid-template-columns: minmax(0, 3fr) minmax(0, 2fr);
  gap: 3vw;
}

.card-hint {
  font-size: 0.9vmax;
  color: var(--app-color-gray);
}

.trend-card,
.insight {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.trend-body {
  display: flex;
  flex-direction: column;
  gap: 1vh;
  padding: 0 1vw 1.5vh;
}

.dist-strip {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.8vh 1vw;
}

.dist-mini {
  display: flex;
  align-items: center;
  gap: 0.6vw;
  font-size: 0.9vmax;
}

.dist-mini-label {
  width: 4.5vw;
  min-width: 52px;
  flex-shrink: 0;
  color: var(--app-color-gray);
}

.dist-mini-bar {
  flex: 1;
  min-width: 0;
  height: 8px;
  border-radius: 100vmax;
  background: var(--app-color-blue-light-5);
  overflow: hidden;
}
.dist-mini-bar i {
  display: block;
  height: 100%;
  border-radius: 100vmax;
  background: linear-gradient(
    90deg,
    var(--app-color-blue-light-2),
    var(--app-color-purple)
  );
}

.dist-mini-value {
  width: 2vw;
  min-width: 20px;
  text-align: right;
  flex-shrink: 0;
  font-weight: bold;
}

/* ============ 今日重要情报 ============ */
.focus-main {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.focus-list {
  display: flex;
  flex-direction: column;
  gap: 1vh;
  padding: 1vh 1vw;
}

.focus-item {
  display: flex;
  align-items: center;
  gap: 1vw;
  padding: 1vh 1vw;
  border-radius: 1vmax;
  box-shadow: 0 1px 10px rgba(0, 0, 0, 0.1);
  cursor: pointer;
  transition: box-shadow 0.2s ease, transform 0.2s ease;
}
.focus-item:hover {
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.14);
  transform: translateY(-1px);
}

/* 图标固定尺寸（:size="44"），不随卡片高度变化 */
.focus-logo {
  flex-shrink: 0;
}

.focus-body {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 0.4vh;
}

.focus-title-row {
  display: flex;
  align-items: center;
  gap: 0.6vw;
  min-width: 0;
}

.focus-ago {
  font-size: 0.9vmax;
  color: var(--app-color-gray);
  margin-left: auto;
  flex-shrink: 0;
}

.focus-title {
  min-width: 0;
  font-size: 1.15vmax;
  font-weight: bold;
  overflow-wrap: anywhere;
}

.focus-summary {
  font-size: 1vmax;
  color: var(--app-text-color-regular);
  overflow-wrap: anywhere;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.empty-hint {
  padding: 3vh 1vw;
  text-align: center;
  font-size: 1vmax;
  color: var(--app-color-gray);
}

.insight-body {
  flex: 1;
  min-width: 0;
  min-height: 120px;
  display: flex;
  flex-direction: column;
  gap: 1vh;
  padding: 1vh 1vw;
}

.insight-badge {
  font-size: 0.85vmax;
  color: var(--app-color-gray);
  padding: 0 0.6vw;
  border-radius: 0.4vmax;
  background: var(--app-color-blue-light-5);
}

.insight-summary {
  margin: 0;
  font-size: 1vmax;
  line-height: 1.7;
  overflow-wrap: anywhere;
}

.insight-points {
  margin: 0;
  padding-left: 1.2vw;
  display: flex;
  flex-direction: column;
  gap: 0.4vh;
  font-size: 0.95vmax;
  color: var(--app-text-color-regular);
}
.insight-points li {
  overflow-wrap: anywhere;
}

.insight-foot {
  margin-top: auto;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1vw;
}

.insight-scope {
  font-size: 0.9vmax;
  color: var(--app-color-gray);
}

/* ============ 竞品动态 ============ */
.dynamics {
  display: flex;
  flex-direction: column;
}

.dynamics-list {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 1vh 1vw;
  padding: 1vh 1vw;
}

.dyn-item {
  display: flex;
  align-items: center;
  gap: 0.6vw;
  min-width: 0;
  padding: 0.8vh 0.8vw;
  border-radius: 1vmax;
  overflow: hidden; /* 兜底：内容再长也不出框 */
  background: var(--app-color-blue-light-5);
}

.dyn-logo {
  flex-shrink: 0;
}

/* 竞品名优先显示：不参与收缩（原来它被挤成 0 宽，导致名字"消失"） */
.dyn-name {
  flex-shrink: 0;
  max-width: 45%;
  font-size: 1vmax;
  font-weight: bold;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* 空间不足时由"变化条数"先让位并省略，而不是牺牲名字 */
.dyn-count {
  flex: 1 1 auto;
  min-width: 0;
  text-align: right;
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 0.9vmax;
  color: var(--app-color-gray);
  white-space: nowrap;
}

.dyn-status {
  display: flex;
  align-items: center;
  gap: 0.3vw;
  font-size: 0.9vmax;
  color: var(--app-color-gray);
  flex-shrink: 0;
}
.dyn-status.active {
  color: var(--app-color-green);
}
.dyn-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--app-text-color-placeholder);
}
.dyn-status.active .dyn-dot {
  background: var(--el-color-success);
}

/* ============ 情报中心入口 ============ */
.center-entry {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 2vw;
  padding: 1.5vh 1.5vw;
}

.entry-left {
  min-width: 0;
}

.entry-title {
  font-size: 1.2vmax;
  font-weight: bold;
}

.entry-desc {
  font-size: 0.95vmax;
  color: var(--app-color-gray);
  margin-top: 0.4vh;
  overflow-wrap: anywhere;
}

.entry-chip {
  display: inline-block;
  margin-right: 0.8vw;
  padding: 0 0.5vw;
  border-radius: 0.4vmax;
  background: var(--app-color-blue-light-5);
  color: var(--app-text-color-regular);
}

.entry-button {
  font-size: 1vmax;
  height: auto;
  white-space: nowrap;
  flex-shrink: 0;
}

@media (max-width: 900px) {
  .stat-cards {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .overview-row {
    grid-template-columns: minmax(0, 1fr);
  }
}

@media (max-width: 640px) {
  .header {
    flex-wrap: wrap;
    gap: 1vh;
  }
  .stat-cards {
    grid-template-columns: minmax(0, 1fr);
    gap: 2vw;
  }
  .onboarding-hint {
    align-items: flex-start;
    flex-direction: column;
  }
  .center-entry {
    flex-direction: column;
    align-items: flex-start;
  }
}
</style>
