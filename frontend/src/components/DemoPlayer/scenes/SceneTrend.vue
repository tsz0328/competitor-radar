<script setup lang="ts">
/**
 * 第四幕：趋势分析 —— 把零散变化读成一条走向
 *
 * 折线用 SVG 手绘（不用图表库），入场靠 pathLength 归一化后的
 * dashoffset 过渡来「描线」，避免引入任何额外依赖。
 */
import { TrendCharts, ArrowUp, Timer, Select } from "@element-plus/icons-vue";

defineProps<{ step: number }>();

const ranges = [
  { label: "近 7 天", on: true },
  { label: "近 30 天" },
  { label: "本季度" },
];

/* 折线坐标系：把原始数值换算成 viewBox 0 0 600 310 里的坐标。
   x 轴 7 个点（9/14 - 9/20），y 轴上限 12。 */
const PLOT = { x0: 44, x1: 580, y0: 24, y1: 270, yMax: 12, steps: 6 };
const xOf = (i: number) => PLOT.x0 + (i * (PLOT.x1 - PLOT.x0)) / PLOT.steps;
const yOf = (v: number) => PLOT.y1 - (v / PLOT.yMax) * (PLOT.y1 - PLOT.y0);

const RAW = [
  {
    key: "linear",
    name: "Linear",
    color: "var(--app-color-blue)",
    values: [3, 5, 4, 8, 6, 11, 9],
  },
  {
    key: "notion",
    name: "Notion",
    color: "var(--app-color-purple)",
    values: [2, 3, 5, 4, 6, 5, 7],
  },
  {
    key: "figma",
    name: "Figma",
    color: "var(--app-color-green)",
    values: [1, 2, 2, 3, 2, 4, 3],
  },
];

const series = RAW.map((s) => ({
  ...s,
  total: s.values.reduce((a, b) => a + b, 0),
  points: s.values.map((v, i) => `${xOf(i)},${yOf(v)}`).join(" "),
  dots: s.values.map((v, i) => ({ x: xOf(i), y: yOf(v) })),
}));

const gridValues = [12, 9, 6, 3, 0];
const dates = ["9/14", "9/15", "9/16", "9/17", "9/18", "9/19", "9/20"];
const ticks = dates.map((_, i) => xOf(i));

const rank = [
  { name: "Linear", word: "L", value: 21, tone: "blue" },
  { name: "Notion", word: "N", value: 12, tone: "purple" },
  { name: "Figma", word: "F", value: 8, tone: "green" },
  { name: "Vercel", word: "V", value: 3, tone: "gray" },
];

const insights = [
  "Linear 活跃度连续 5 天上升，本周变化量为近 8 周最高",
  "Notion 的变化集中在定价页，且集中在工作时段，属于人工调整",
  "Figma 走势平缓，最近一次大动作已过去 3 周",
];
</script>

<template>
  <div class="head">
    <div>
      <div class="h1">趋势分析</div>
      <div class="h2">基于 42 条情报事件聚合 · 覆盖 4 个竞品</div>
    </div>
    <div class="ctrl">
      <div class="ranges">
        <i
          v-for="r in ranges"
          :key="r.label"
          class="range"
          :class="{ 'range--on': r.on }"
          >{{ r.label }}</i
        >
      </div>
      <i class="pick">
        <el-icon><Select /></el-icon>
        <span>全部竞品</span>
      </i>
    </div>
  </div>

  <div class="body">
    <!-- 折线图 -->
    <section class="chart-card">
      <div class="chart-head">
        <div class="chart-title">
          <el-icon><TrendCharts /></el-icon>
          <span>竞品情报变化趋势</span>
        </div>
        <div class="legend">
          <span v-for="s in series" :key="s.key" class="legend-item">
            <i class="legend-dot" :style="{ background: s.color }" />
            {{ s.name }}
          </span>
        </div>
      </div>

      <svg class="chart" viewBox="0 0 600 310" preserveAspectRatio="xMidYMid meet">
        <line
          v-for="v in gridValues"
          :key="`g-${v}`"
          x1="44"
          :y1="yOf(v)"
          x2="580"
          :y2="yOf(v)"
          stroke="color-mix(in oklab, var(--app-color-blue) 14%, transparent)"
          stroke-width="1.5"
          stroke-dasharray="4 6"
        />
        <text
          v-for="v in gridValues"
          :key="`gl-${v}`"
          x="36"
          :y="yOf(v) + 4"
          text-anchor="end"
          font-size="11"
          fill="var(--app-text-color-placeholder)"
        >
          {{ v }}
        </text>

        <g v-for="(s, i) in series" :key="s.key">
          <polyline
            class="line"
            :class="{ 'line--in': step >= 1 && i === 0, 'line--more': step >= 2 }"
            :points="s.points"
            fill="none"
            :stroke="s.color"
            stroke-width="3"
            stroke-linecap="round"
            stroke-linejoin="round"
            pathLength="1"
            :style="{ transitionDelay: `${i * 0.22}s` }"
          />
          <g v-if="step >= 2">
            <circle
              v-for="(d, j) in s.dots"
              :key="`${s.key}-${j}`"
              :cx="d.x"
              :cy="d.y"
              r="3.4"
              :fill="s.color"
            />
          </g>
        </g>

        <text
          v-for="(d, i) in dates"
          :key="d"
          :x="ticks[i]"
          y="296"
          text-anchor="middle"
          font-size="11"
          fill="var(--app-text-color-placeholder)"
        >
          {{ d }}
        </text>
      </svg>
    </section>

    <!-- 右侧洞察 -->
    <aside class="side">
      <div class="insight-card" :class="{ 'insight-card--on': step >= 3 }">
        <div class="insight-tag">
          <el-icon><ArrowUp /></el-icon>
          <span>活跃度上升</span>
        </div>
        <p class="insight-text">
          近 7 天 4 个竞品共产生 42 条变化，环比上涨 27%，为本季度最高。
          主要增量来自 Linear 的排期自动化与 Notion 的定价调整。
        </p>
        <ul class="insight-list">
          <li v-for="(t, i) in insights" :key="t" :style="{ transitionDelay: `${i * 0.14}s` }">
            {{ t }}
          </li>
        </ul>
      </div>

      <div class="rank-card">
        <div class="rank-title">竞品活跃度 · 本周</div>
        <div v-for="r in rank" :key="r.name" class="rank-row">
          <i class="rank-logo" :class="`rank-logo--${r.tone}`">{{ r.word }}</i>
          <span class="rank-name">{{ r.name }}</span>
          <span class="rank-bar">
            <i
              class="rank-bar-fill"
              :class="`rank-bar-fill--${r.tone}`"
              :style="{ width: `${(r.value / 21) * 100}%` }"
            />
          </span>
          <span class="rank-value">{{ r.value }}</span>
        </div>
      </div>

      <div class="tip">
        <el-icon><Timer /></el-icon>
        <span>数据每晚 08:00 自动更新</span>
      </div>
    </aside>
  </div>
</template>

<style scoped>
.head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  flex: 0 0 auto;
}
.h1 {
  font-size: 21px;
  font-weight: 600;
}
.h2 {
  margin-top: 3px;
  font-size: 13px;
  color: var(--app-text-color-secondary);
}
.ctrl {
  display: flex;
  align-items: center;
  gap: 10px;
}
.ranges {
  display: flex;
  gap: 4px;
  padding: 3px;
  border-radius: 13px;
  background: color-mix(in oklab, var(--app-color-blue) 7%, transparent);
}
.range {
  height: 28px;
  padding: 0 13px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  font-size: 12.5px;
  font-style: normal;
  color: var(--app-text-color-secondary);
}
.range--on {
  font-weight: 600;
  color: var(--app-color-blue);
  background: var(--app-color-white);
  box-shadow: 0 1px 4px color-mix(in oklab, var(--app-color-blue) 24%, transparent);
}
.pick {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 34px;
  padding: 0 13px;
  border-radius: 11px;
  font-size: 13px;
  font-style: normal;
  color: var(--app-text-color-secondary);
  background: color-mix(in oklab, var(--app-color-blue) 6%, transparent);
  border: 2px solid color-mix(in oklab, var(--app-color-blue) 15%, transparent);
}

.body {
  flex: 1;
  min-height: 0;
  display: flex;
  gap: 16px;
}

/* ---------- 折线图 ---------- */
.chart-card {
  flex: 1;
  min-width: 0;
  padding: 16px 18px;
  border-radius: 18px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  background: color-mix(in oklab, var(--app-color-white) 90%, var(--app-color-blue));
  border: 2px solid color-mix(in oklab, var(--app-color-blue) 15%, transparent);
}
.chart-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
.chart-title {
  display: flex;
  align-items: center;
  gap: 7px;
  font-size: 14.5px;
  font-weight: 600;
}
.chart-title .el-icon {
  color: var(--app-color-blue);
}
.legend {
  display: flex;
  gap: 14px;
}
.legend-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--app-text-color-secondary);
}
.legend-dot {
  width: 9px;
  height: 9px;
  border-radius: 3px;
}
.chart {
  flex: 1;
  min-height: 0;
  width: 100%;
}
.line {
  stroke-dasharray: 1;
  stroke-dashoffset: 1;
  transition: stroke-dashoffset 1.1s ease-in-out;
}
.line--in {
  stroke-dashoffset: 0;
}
.line--more {
  stroke-dashoffset: 0;
}

/* ---------- 右侧 ---------- */
.side {
  flex: 0 0 auto;
  width: 308px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.insight-card {
  padding: 13px 15px;
  border-radius: 16px;
  display: flex;
  flex-direction: column;
  gap: 9px;
  background: color-mix(in oklab, var(--app-color-purple) 7%, transparent);
  border: 2px solid transparent;
  transition: border-color 0.5s ease, box-shadow 0.5s ease;
}
.insight-card--on {
  border-color: color-mix(in oklab, var(--app-color-purple) 42%, transparent);
  box-shadow: 0 0 0 4px color-mix(in oklab, var(--app-color-purple) 13%, transparent);
}
.insight-tag {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  align-self: flex-start;
  height: 24px;
  padding: 0 10px;
  border-radius: 9px;
  font-size: 12px;
  font-weight: 600;
  color: var(--app-color-purple);
  background: color-mix(in oklab, var(--app-color-purple) 14%, transparent);
}
.insight-text {
  margin: 0;
  font-size: 12.5px;
  line-height: 1.6;
  color: var(--app-text-color-regular);
}
.insight-list {
  margin: 0;
  padding-left: 15px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.insight-list li {
  font-size: 12px;
  line-height: 1.5;
  color: var(--app-text-color-secondary);
}
.rank-card {
  padding: 13px 15px;
  border-radius: 16px;
  display: flex;
  flex-direction: column;
  gap: 9px;
  background: color-mix(in oklab, var(--app-color-white) 90%, var(--app-color-blue));
  border: 2px solid color-mix(in oklab, var(--app-color-blue) 13%, transparent);
}
.rank-title {
  font-size: 12.5px;
  font-weight: 600;
  color: var(--app-text-color-secondary);
}
.rank-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.rank-logo {
  flex: 0 0 auto;
  width: 22px;
  height: 22px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11.5px;
  font-style: normal;
  font-weight: 600;
  color: var(--app-color-white);
}
.rank-logo--blue {
  background: var(--app-color-blue);
}
.rank-logo--purple {
  background: var(--app-color-purple);
}
.rank-logo--green {
  background: var(--app-color-green);
}
.rank-logo--gray {
  background: var(--app-color-gray);
}
.rank-name {
  flex: 0 0 auto;
  width: 52px;
  font-size: 12.5px;
}
.rank-bar {
  flex: 1;
  min-width: 0;
  height: 8px;
  border-radius: 5px;
  overflow: hidden;
  background: color-mix(in oklab, var(--app-color-blue) 10%, transparent);
}
.rank-bar-fill {
  display: block;
  height: 100%;
  border-radius: 5px;
}
.rank-bar-fill--blue {
  background: var(--app-color-blue);
}
.rank-bar-fill--purple {
  background: var(--app-color-purple);
}
.rank-bar-fill--green {
  background: var(--app-color-green);
}
.rank-bar-fill--gray {
  background: var(--app-color-gray);
}
.rank-value {
  flex: 0 0 auto;
  width: 20px;
  text-align: right;
  font-size: 12.5px;
  font-weight: 600;
}
.tip {
  margin-top: auto;
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11.5px;
  color: var(--app-text-color-placeholder);
}
</style>
