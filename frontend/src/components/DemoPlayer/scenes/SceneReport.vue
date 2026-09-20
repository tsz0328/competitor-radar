<script setup lang="ts">
/**
 * 第三幕：周度报告 —— 一键把这周的情报写成周报
 *
 * 四个步骤按真实使用顺序推进：点生成 → AI 汇总过程 → 报告正文 → 核心数据。
 * 正文里的要点、统计数字都是写死的模拟数据。
 */
import { Document, MagicStick, Star, Check, Loading } from "@element-plus/icons-vue";

defineProps<{ step: number }>();

const reports = [
  { title: "2026年第38周 竞品周报", range: "9月14日 - 9月20日", count: 4, current: true },
  { title: "2026年第37周 竞品周报", range: "9月7日 - 9月13日", count: 4 },
  { title: "2026年第36周 竞品周报", range: "8月31日 - 9月6日", count: 3 },
];

const aiSteps = [
  { title: "汇总本周情报", desc: "抓取 11 个页面，识别 42 条变化", done: true },
  { title: "归并同类变化", desc: "去掉重复与微调，保留 18 条有效变化", done: true },
  { title: "生成影响判断", desc: "结合历史基线与行业背景给出解读", done: false },
];

const highlights = [
  {
    tag: "价格变化",
    tone: "price",
    impact: "高影响",
    title: "Notion 团队版月付下调 15%，年付未变",
    points: [
      "Teams 档位由 $18 降至 $15.3 / 席位 / 月",
      "年付价格与 AI 额度均未调整",
      "大概率是针对小团队的获客动作",
    ],
    brands: ["Notion"],
  },
  {
    tag: "功能更新",
    tone: "feat",
    impact: "高影响",
    title: "Linear 上线 Cycles 自动滚动，排期自动化再进一步",
    points: [
      "更新日志新增「Auto-rollover」小节",
      "定价页同步出现新模块入口",
      "踩到 Jira 与 Asana 的同一战场",
    ],
    brands: ["Linear"],
  },
];

const stats = [
  { label: "情报事件", value: "42", delta: "27%", up: true },
  { label: "覆盖竞品", value: "4", delta: "0", up: true },
  { label: "功能更新", value: "18", delta: "12%", up: true },
  { label: "价格变化", value: "6", delta: "8%", up: false },
  { label: "高影响", value: "7", delta: "40%", up: true },
];

const bars = [
  { d: "9/14", cur: 32, prev: 26 },
  { d: "9/15", cur: 46, prev: 30 },
  { d: "9/16", cur: 38, prev: 34 },
  { d: "9/17", cur: 62, prev: 40 },
  { d: "9/18", cur: 54, prev: 36 },
  { d: "9/19", cur: 78, prev: 44 },
  { d: "9/20", cur: 66, prev: 38 },
];
</script>

<template>
  <div class="head">
    <div>
      <div class="h1">周度报告</div>
      <div class="h2">已归档 12 期 · 每周一 09:00 自动生成</div>
    </div>
    <div class="btn" :class="{ 'btn--on': step === 0 }">
      <el-icon><MagicStick /></el-icon>
      <span>生成周报</span>
    </div>
  </div>

  <div class="body">
    <!-- 左侧报告列表 -->
    <aside class="list">
      <div class="list-title">历史周报</div>
      <div
        v-for="r in reports"
        :key="r.title"
        class="item"
        :class="{ 'item--on': r.current }"
      >
        <el-icon class="item-icon"><Document /></el-icon>
        <div class="item-main">
          <div class="item-title">{{ r.title }}</div>
          <div class="item-sub">{{ r.range }} · {{ r.count }} 个竞品</div>
        </div>
        <el-icon v-if="r.current && step >= 2" class="item-star"><Star /></el-icon>
      </div>
    </aside>

    <!-- 右侧报告正文 -->
    <section class="report">
      <!-- 还没生成 -->
      <div v-if="step === 0" class="empty">
        <el-icon class="empty-icon"><Document /></el-icon>
        <div class="empty-title">本周周报尚未生成</div>
        <div class="empty-sub">基于 4 个竞品、11 个监控页面、42 条情报事件生成</div>
      </div>

      <!-- 生成中 -->
      <div v-else-if="step === 1" class="gen">
        <div class="gen-title">AI 正在汇总本周情报…</div>
        <div class="gen-bar"><i class="gen-bar-fill" /></div>
        <div
          v-for="(s, i) in aiSteps"
          :key="s.title"
          class="gen-step"
          :class="{ 'gen-step--on': i <= 1 }"
          :style="{ transitionDelay: `${i * 0.18}s` }"
        >
          <el-icon class="gen-step-icon">
            <Check v-if="s.done" />
            <Loading v-else />
          </el-icon>
          <div>
            <div class="gen-step-title">{{ s.title }}</div>
            <div class="gen-step-desc">{{ s.desc }}</div>
          </div>
        </div>
      </div>

      <!-- 报告正文 -->
      <template v-else>
        <div class="rep-head">
          <div class="rep-title">2026年第38周 竞品周报</div>
          <div class="rep-meta">
            覆盖 9月14日 - 9月20日 · 4 个竞品 · 生成于 2026-09-20 09:00
          </div>
        </div>

        <p class="rep-summary">
          本周 4 个监控竞品共产生 42 条变化，环比上涨 27%。最值得关注的是
          Notion 与 Linear 两家同时动了「价格」和「排期自动化」，同价位工具的比价空间被压缩。
        </p>

        <div class="hl-wrap">
          <div class="block-label">本周重点变化</div>
          <div class="hl-list">
            <div
              v-for="(h, i) in highlights"
              :key="h.title"
              class="hl"
              :class="{ 'hl--on': step >= 2 }"
              :style="{ transitionDelay: `${i * 0.14}s` }"
            >
              <div class="hl-top">
                <i class="tag" :class="`tag--${h.tone}`">{{ h.tag }}</i>
                <i class="impact">{{ h.impact }}</i>
                <em
                  v-for="b in h.brands"
                  :key="b"
                  class="brand"
                  >{{ b }}</em
                >
              </div>
              <div class="hl-title">{{ h.title }}</div>
              <ul class="hl-points">
                <li v-for="p in h.points" :key="p">{{ p }}</li>
              </ul>
            </div>
          </div>
        </div>

        <div class="data" :class="{ 'data--in': step >= 3 }">
          <div class="data-stats">
            <div v-for="s in stats" :key="s.label" class="stat">
              <div class="stat-label">{{ s.label }}</div>
              <div class="stat-value">{{ s.value }}</div>
              <div class="stat-delta" :class="{ 'stat-delta--down': !s.up }">
                {{ s.up ? "↑" : "↓" }} {{ s.delta }}
              </div>
            </div>
          </div>
          <div class="data-chart">
            <div class="chart-label">高影响事件趋势 · 本周 vs 上周</div>
            <div class="chart-bars">
              <div v-for="b in bars" :key="b.d" class="bar-group">
                <i class="bar bar--prev" :style="{ height: `${b.prev * 0.72}px` }" />
                <i class="bar bar--cur" :style="{ height: `${b.cur * 0.72}px` }" />
                <span class="bar-date">{{ b.d }}</span>
              </div>
            </div>
          </div>
        </div>
      </template>
    </section>
  </div>
</template>

<style scoped>
.head {
  display: flex;
  align-items: center;
  justify-content: space-between;
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
.btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 36px;
  padding: 0 15px;
  border-radius: 12px;
  font-size: 14px;
  font-weight: 600;
  color: var(--app-color-white);
  background: var(--app-color-purple);
  border: 2px solid color-mix(in oklab, var(--app-color-purple) 70%, var(--app-color-black));
  transition: box-shadow 0.4s ease, transform 0.4s ease;
}
.btn--on {
  transform: translateY(-2px);
  box-shadow: 0 0 0 4px color-mix(in oklab, var(--app-color-purple) 28%, transparent);
}

.body {
  flex: 1;
  min-height: 0;
  display: flex;
  gap: 16px;
}

/* ---------- 左列表 ---------- */
.list {
  flex: 0 0 auto;
  width: 188px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.list-title {
  font-size: 12.5px;
  font-weight: 600;
  color: var(--app-text-color-secondary);
}
.item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 11px;
  border-radius: 14px;
  background: color-mix(in oklab, var(--app-color-white) 86%, var(--app-color-blue));
  border: 2px solid transparent;
  transition: border-color 0.4s ease;
}
.item--on {
  background: color-mix(in oklab, var(--app-color-purple) 11%, var(--app-color-white));
  border-color: color-mix(in oklab, var(--app-color-purple) 34%, transparent);
}
.item-icon {
  flex: 0 0 auto;
  font-size: 15px;
  color: var(--app-color-purple);
}
.item-main {
  flex: 1;
  min-width: 0;
}
.item-title {
  font-size: 12.5px;
  font-weight: 600;
  line-height: 1.3;
}
.item-sub {
  margin-top: 3px;
  font-size: 11px;
  color: var(--app-text-color-placeholder);
}
.item-star {
  flex: 0 0 auto;
  font-size: 13px;
  color: var(--app-color-orange);
}

/* ---------- 右报告 ---------- */
.report {
  flex: 1;
  min-width: 0;
  padding: 18px 20px;
  border-radius: 18px;
  display: flex;
  flex-direction: column;
  gap: 13px;
  overflow: hidden;
  background: color-mix(in oklab, var(--app-color-white) 90%, var(--app-color-purple));
  border: 2px solid color-mix(in oklab, var(--app-color-purple) 16%, transparent);
}
.empty {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
}
.empty-icon {
  font-size: 34px;
  color: color-mix(in oklab, var(--app-color-purple) 40%, transparent);
}
.empty-title {
  font-size: 15px;
  font-weight: 600;
}
.empty-sub {
  font-size: 12.5px;
  color: var(--app-text-color-secondary);
}

.gen {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding-top: 6px;
}
.gen-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--app-color-purple);
}
.gen-bar {
  height: 8px;
  border-radius: 5px;
  overflow: hidden;
  background: color-mix(in oklab, var(--app-color-purple) 13%, transparent);
}
.gen-bar-fill {
  display: block;
  height: 100%;
  width: 68%;
  border-radius: 5px;
  background: var(--app-color-purple);
  animation: genGrow 2.2s ease-in-out infinite alternate;
}
@keyframes genGrow {
  from {
    width: 34%;
  }
  to {
    width: 82%;
  }
}
.gen-step {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 11px 13px;
  border-radius: 13px;
  opacity: 0;
  transform: translateX(-8px);
  transition: opacity 0.5s ease, transform 0.5s ease;
  background: color-mix(in oklab, var(--app-color-purple) 5%, transparent);
}
.gen-step--on {
  opacity: 1;
  transform: translateX(0);
}
.gen-step-icon {
  flex: 0 0 auto;
  margin-top: 2px;
  font-size: 14px;
  color: var(--app-color-green);
}
.gen-step-title {
  font-size: 13.5px;
  font-weight: 600;
}
.gen-step-desc {
  margin-top: 2px;
  font-size: 12px;
  color: var(--app-text-color-secondary);
}

.rep-head {
  flex: 0 0 auto;
}
.rep-title {
  font-size: 18px;
  font-weight: 600;
}
.rep-meta {
  margin-top: 4px;
  font-size: 12px;
  color: var(--app-text-color-placeholder);
}
.rep-summary {
  flex: 0 0 auto;
  margin: 0;
  font-size: 13px;
  line-height: 1.65;
  padding: 11px 13px;
  border-radius: 13px;
  color: var(--app-text-color-regular);
  background: color-mix(in oklab, var(--app-color-purple) 7%, transparent);
}
.hl-wrap {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
  overflow: hidden;
}
.block-label {
  font-size: 12.5px;
  font-weight: 600;
  color: var(--app-text-color-secondary);
}
.hl-list {
  display: flex;
  flex-direction: column;
  gap: 9px;
}
.hl {
  padding: 11px 13px;
  border-radius: 13px;
  opacity: 0;
  transform: translateY(8px);
  transition: opacity 0.5s ease, transform 0.5s ease;
  background: color-mix(in oklab, var(--app-color-white) 94%, var(--app-color-purple));
  border: 2px solid color-mix(in oklab, var(--app-color-purple) 15%, transparent);
}
.hl--on {
  opacity: 1;
  transform: translateY(0);
}
.hl-top {
  display: flex;
  align-items: center;
  gap: 7px;
  margin-bottom: 6px;
}
.tag {
  display: inline-flex;
  align-items: center;
  height: 20px;
  padding: 0 8px;
  border-radius: 7px;
  font-size: 11px;
  font-style: normal;
  font-weight: 600;
}
.tag--price {
  color: var(--app-color-red);
  background: color-mix(in oklab, var(--app-color-red) 13%, transparent);
}
.tag--feat {
  color: var(--app-color-blue);
  background: color-mix(in oklab, var(--app-color-blue) 13%, transparent);
}
.impact {
  font-style: normal;
  font-size: 11px;
  padding: 1px 7px;
  border-radius: 6px;
  color: var(--app-color-orange);
  border: 1.5px solid color-mix(in oklab, var(--app-color-orange) 38%, transparent);
}
.brand {
  font-style: normal;
  font-size: 11.5px;
  color: var(--app-text-color-secondary);
}
.hl-title {
  font-size: 13.5px;
  font-weight: 600;
}
.hl-points {
  margin: 6px 0 0;
  padding-left: 16px;
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.hl-points li {
  font-size: 12px;
  line-height: 1.5;
  color: var(--app-text-color-secondary);
}

/* ---------- 核心数据 ---------- */
.data {
  flex: 0 0 auto;
  height: 232px;
  display: flex;
  gap: 16px;
  opacity: 0;
  transform: translateY(12px);
  transition: opacity 0.55s ease, transform 0.55s ease;
}
.data--in {
  opacity: 1;
  transform: translateY(0);
}
.data-stats {
  flex: 0 0 auto;
  width: 296px;
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 8px;
}
.stat {
  padding: 9px 11px;
  border-radius: 12px;
  background: color-mix(in oklab, var(--app-color-blue) 6%, transparent);
  border: 1.5px solid color-mix(in oklab, var(--app-color-blue) 14%, transparent);
}
.stat:first-child {
  grid-column: span 2;
}
.stat-label {
  font-size: 11.5px;
  color: var(--app-text-color-secondary);
}
.stat-value {
  font-size: 20px;
  font-weight: 600;
  line-height: 1.2;
}
.stat-delta {
  font-size: 11.5px;
  font-weight: 600;
  color: var(--app-color-green);
}
.stat-delta--down {
  color: var(--app-color-red);
}
.data-chart {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 11px 13px;
  border-radius: 12px;
  background: color-mix(in oklab, var(--app-color-blue) 5%, transparent);
  border: 1.5px solid color-mix(in oklab, var(--app-color-blue) 14%, transparent);
}
.chart-label {
  font-size: 11.5px;
  color: var(--app-text-color-secondary);
}
.chart-bars {
  flex: 1;
  display: flex;
  align-items: flex-end;
  gap: 10px;
}
.bar-group {
  flex: 1;
  display: flex;
  align-items: flex-end;
  justify-content: center;
  gap: 3px;
  position: relative;
  padding-bottom: 15px;
  height: 100%;
}
.bar {
  width: 9px;
  border-radius: 4px 4px 0 0;
}
.bar--prev {
  background: color-mix(in oklab, var(--app-color-blue) 26%, transparent);
}
.bar--cur {
  background: var(--app-color-purple);
}
.bar-date {
  position: absolute;
  bottom: 0;
  font-size: 10px;
  color: var(--app-text-color-placeholder);
}
</style>
