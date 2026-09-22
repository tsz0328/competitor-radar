<script setup lang="ts">
/**
 * 平台总览（仅管理员）：全局总量卡片 + 近 30 天情报/抓取趋势。
 * 只读统计页——管理员在这里看的是「用户们的整体数据」，不做业务操作。
 */
import { computed, onMounted, ref } from "vue";
import VChart from "vue-echarts";
import { use } from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import { LineChart } from "echarts/charts";
import {
  GridComponent,
  LegendComponent,
  TooltipComponent,
  GraphicComponent,
} from "echarts/components";
import { useRouter } from "vue-router";
import { UserFilled, Key, OfficeBuilding, List, Document, Tickets, Refresh } from "@element-plus/icons-vue";
import { getAdminOverview, type AdminOverview } from "@/api/admin";

use([
  CanvasRenderer,
  LineChart,
  GridComponent,
  LegendComponent,
  TooltipComponent,
  GraphicComponent,
]);

const router = useRouter();

const loading = ref(false);
const loadError = ref(false);
const overview = ref<AdminOverview | null>(null);

async function load() {
  loading.value = true;
  loadError.value = false;
  try {
    overview.value = await getAdminOverview();
  } catch {
    // 错误提示由 request.ts 统一弹出，这里只记录状态用于展示重试条
    overview.value = null;
    loadError.value = true;
  } finally {
    loading.value = false;
  }
}

const totals = computed(() => overview.value?.totals);

// 总量卡片：回答「平台上有多少用户、每天产出多少数据」
const statCards = computed(() => [
  {
    key: "users",
    title: "注册用户",
    value: totals.value?.users ?? "-",
    desc: `启用 ${totals.value?.active_users ?? "-"} 人`,
    icon: UserFilled,
    cls: "icon-blue",
  },
  {
    key: "admins",
    title: "管理员",
    value: totals.value?.admin_users ?? "-",
    desc: totals.value?.users
      ? `占注册用户 ${Math.round(((totals.value?.admin_users ?? 0) / totals.value.users) * 100)}%`
      : "平台运营账号",
    icon: Key,
    cls: "icon-purple",
  },
  {
    key: "competitors",
    title: "监控竞品",
    value: totals.value?.competitors ?? "-",
    desc: `共 ${totals.value?.sources ?? "-"} 个监控源`,
    icon: OfficeBuilding,
    cls: "icon-purple",
  },
  {
    key: "events",
    title: "情报事件",
    value: totals.value?.events ?? "-",
    desc: "累计产出",
    icon: List,
    cls: "icon-orange",
  },
  {
    key: "reports",
    title: "周度报告",
    value: totals.value?.reports ?? "-",
    desc: "未删除",
    icon: Document,
    cls: "icon-green",
  },
  {
    key: "crawls",
    title: "抓取次数",
    value: totals.value?.crawl_logs ?? "-",
    desc: "累计",
    icon: Tickets,
    cls: "icon-blue",
  },
]);

/** 可点击（跳转）卡片 → 目标路由：users/admins 跳用户管理，competitors 跳全部竞品，情报/周报/抓取跳平台数据对应 tab */
const CLICKABLE_STAT_KEYS = new Set(["users", "admins", "competitors", "events", "reports", "crawls"]);
function isStatCardClickable(card: { key: string }) {
  return CLICKABLE_STAT_KEYS.has(card.key);
}
function onStatCardClick(card: { key: string }) {
  if (card.key === "competitors") {
    router.push({ name: "AdminCompetitors" });
  } else if (card.key === "users" || card.key === "admins") {
    router.push({ name: "UserManage" });
  } else {
    // events / reports / crawls → 平台数据页对应 tab
    router.push({ name: "AdminData", query: { tab: card.key } });
  }
}

// 近 30 天双折线：情报事件 + 抓取次数
const chartOption = computed(() => {
  const eventTrend = overview.value?.event_trend ?? [];
  const crawlTrend = overview.value?.crawl_trend ?? [];
  if (!eventTrend.length) {
    return {
      graphic: [
        {
          type: "text",
          left: "center",
          top: "center",
          style: { text: "暂无趋势数据", fill: "#a8adb3", fontSize: 14 },
        },
      ],
      xAxis: { show: false },
      yAxis: { show: false },
      series: [],
    };
  }
  const COLORS = {
    textPlaceholder: "#a8adb3",
    border: "#e5e7eb",
  };
  return {
    tooltip: {
      trigger: "axis",
      backgroundColor: "#fff",
      borderColor: COLORS.border,
      textStyle: { color: "#303133", fontSize: 13 },
    },
    legend: {
      top: 0,
      right: 12,
      itemWidth: 14,
      itemHeight: 8,
      textStyle: { color: COLORS.textPlaceholder, fontSize: 12 },
    },
    grid: { left: 12, right: 16, bottom: 8, top: 32, containLabel: true },
    xAxis: {
      type: "category",
      boundaryGap: false,
      data: eventTrend.map((d) => d.date),
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: {
        color: COLORS.textPlaceholder,
        fontSize: 12,
        interval: Math.max(0, Math.floor(eventTrend.length / 7) - 1),
      },
    },
    yAxis: {
      type: "value",
      splitLine: { lineStyle: { type: "dashed", color: COLORS.border } },
      axisLabel: { color: COLORS.textPlaceholder, fontSize: 12 },
    },
    series: [
      {
        name: "情报事件",
        type: "line",
        smooth: true,
        symbol: "circle",
        symbolSize: 6,
        showSymbol: false,
        lineStyle: { width: 2.5, color: "#2f6bff" },
        itemStyle: { color: "#2f6bff" },
        areaStyle: { opacity: 0.08 },
        data: eventTrend.map((d) => d.count),
      },
      {
        name: "抓取次数",
        type: "line",
        smooth: true,
        symbol: "circle",
        symbolSize: 6,
        showSymbol: false,
        lineStyle: { width: 2.5, color: "#7c5cf0" },
        itemStyle: { color: "#7c5cf0" },
        areaStyle: { opacity: 0.08 },
        data: crawlTrend.map((d) => d.count),
      },
    ],
  };
});

onMounted(load);
</script>
<template>
  <div class="admin-overview">
    <header class="header">
      <div>
        <div class="title">平台总览</div>
        <div class="subtitle">全部用户的监控、情报与报告整体情况</div>
      </div>
      <div class="actions">
        <el-button :icon="Refresh" :loading="loading" @click="load">刷新</el-button>
      </div>
    </header>

    <!-- 加载失败：数据清空 + 给出重试入口（接口错误提示已在 request.ts 弹出） -->
    <section v-if="loadError" class="error-banner">
      <span>平台总览数据加载失败，请稍后重试。</span>
      <el-button link type="primary" @click="load">重新加载</el-button>
    </section>

    <!-- 指标卡：平台全局总量 -->
    <section class="stat-cards">
      <div
        v-for="card in statCards"
        :key="card.key"
        class="stat-card card"
        :class="{ 'stat-card--clickable': isStatCardClickable(card) }"
        v-loading="loading"
        @click="onStatCardClick(card)"
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

    <!-- 近 30 天趋势：加载失败时不渲染，避免把错误误显示成「暂无数据」 -->
    <section v-if="!loadError" class="card trend-card">
      <header class="card-head">
        <span class="card-title">近 30 天趋势</span>
        <span class="card-hint">情报事件与抓取次数（全部用户）</span>
      </header>
      <v-chart
        class="trend-chart"
        :option="chartOption"
        autoresize
        :loading="loading"
      />
    </section>
  </div>
</template>
<style scoped>
.card {
  background-color: var(--app-color-white);
  border-radius: 1vmax;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.1);
}
.admin-overview {
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
.actions {
  display: flex;
  gap: 0.5vw;
}

/* 6 张卡按 3 列排两行 */
.stat-cards {
  flex-shrink: 0;
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 2vw;
}

.stat-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1.5vh 1.2vw;
}

.stat-card--clickable {
  cursor: pointer;
  transition: box-shadow 0.2s ease, transform 0.15s ease,
    border-color 0.2s ease;
}
.stat-card--clickable:hover {
  box-shadow: 0 12px 30px -10px rgba(15, 23, 42, 0.22);
  transform: translateY(-3px);
  /* 悬停泛起主紫描边，与用户端品牌色一致 */
  border-color: color-mix(
    in oklch,
    var(--app-color-purple) 45%,
    oklch(92.5% 0.005 260)
  );
}
.stat-card--clickable:active {
  transform: translateY(0);
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.1);
}

.stat-card-content {
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.stat-card-title {
  font-size: 1.1vmax;
  font-weight: bold;
  letter-spacing: 0.05em;
}
.stat-card-value {
  font-size: 1.7vmax;
  font-weight: bold;
  font-variant-numeric: tabular-nums;
  letter-spacing: 0.02em;
}
.stat-card-desc {
  font-size: 0.9vmax;
  color: var(--app-color-gray);
}

.stat-card-icon {
  width: 4vmax;
  height: 4vmax;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1.8vmax;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.7),
    0 8px 18px -10px rgba(15, 23, 42, 0.35);
}
.icon-blue {
  background: linear-gradient(
    135deg,
    var(--app-color-blue-light-2),
    var(--app-color-blue-light-4)
  );
  color: var(--app-color-blue-dark-2);
}
.icon-purple {
  background: linear-gradient(
    135deg,
    var(--app-color-purple-light-2),
    var(--app-color-purple-light-4)
  );
  color: var(--app-color-purple-dark-2);
}
.icon-orange {
  background: linear-gradient(
    135deg,
    var(--app-color-orange-light-2),
    var(--app-color-orange-light-4)
  );
  color: var(--app-color-orange-dark-2);
}
.icon-green {
  background: linear-gradient(
    135deg,
    var(--app-color-green-light-2),
    var(--app-color-green-light-4)
  );
  color: var(--app-color-green-dark-2);
}

/* 加载失败提示条：与工作台引导条同款版式，橙色表达「需关注」 */
.error-banner {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1vw;
  padding: 1vh 1vw;
  border-radius: 1vmax;
  background: var(--app-color-orange-light-5);
  color: var(--app-text-color-regular);
  font-size: 1vmax;
}

.trend-card {
  padding: 1.5vh 1.2vw;
  display: flex;
  flex-direction: column;
  gap: 1vh;
}
.card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 2vw;
}
.card-title {
  font-size: 1.1vmax;
  font-weight: bold;
}
.card-hint {
  font-size: 0.9vmax;
  color: var(--app-color-gray);
}
.trend-chart {
  height: 300px;
  width: 100%;
  display: block;
}

/* 窄屏时指标卡从 3 列降为 2 列 / 1 列，避免卡片被挤扁 */
@media (max-width: 900px) {
  .stat-cards {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 640px) {
  .stat-cards {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>