<script setup lang="ts">
/**
 * 第二幕：情报中心 —— 抓取比对，找出「变了什么」
 *
 * 左侧情报流 + 右侧详情抽屉。抽屉里刻意把「AI 摘要（事实）」
 * 与「AI 影响判断（观点）」分开呈现，和真实产品保持一致。
 */
import { ArrowRight, Document, Close } from "@element-plus/icons-vue";

defineProps<{ step: number }>();

const summary = [
  { label: "全部", value: 42, on: true },
  { label: "功能更新", value: 18 },
  { label: "价格变化", value: 6 },
  { label: "内容更新", value: 12 },
  { label: "其他", value: 6 },
];

const groups = [
  {
    dateLabel: "今天",
    items: [
      {
        brand: "Linear",
        word: "L",
        tag: "功能更新",
        tone: "feat",
        time: "10:24",
        priority: "高优先级",
        title: "Linear 上线 Cycles 自动滚动",
        desc: "更新日志新增「Auto-rollover」小节，定价页同步出现新模块入口",
        confidence: 92,
      },
      {
        brand: "Notion",
        word: "N",
        tag: "价格变化",
        tone: "price",
        time: "09:05",
        priority: "高优先级",
        title: "Notion AI 团队版月付下调 15%",
        desc: "定价页 Teams 档位由 $18 / 席位 / 月 调整为 $15.3，年付不变",
        confidence: 88,
      },
    ],
  },
  {
    dateLabel: "昨天",
    items: [
      {
        brand: "Figma",
        word: "F",
        tag: "内容更新",
        tone: "content",
        time: "18:40",
        priority: "中优先级",
        title: "Figma 博客新增设计系统白皮书",
        desc: "博客页新增 1 篇长文，约 4200 字，含 6 张对比图",
        confidence: 76,
      },
      {
        brand: "Vercel",
        word: "V",
        tag: "功能更新",
        tone: "feat",
        time: "15:12",
        priority: "中优先级",
        title: "Vercel 边缘函数默认区域调整",
        desc: "文档页 3 处变更，默认执行区域由 iad1 改为自动就近",
        confidence: 81,
      },
    ],
  },
];

const foundPages = ["定价页", "更新日志"];
</script>

<template>
  <div class="head">
    <div>
      <div class="h1">情报中心</div>
      <div class="h2">今天新增 7 条变化 · 高优先级 2 条 · 已自动去重</div>
    </div>
    <div class="filters">
      <i
        v-for="s in summary"
        :key="s.label"
        class="fchip"
        :class="{ 'fchip--on': s.on }"
      >
        {{ s.label }}
        <b>{{ s.value }}</b>
      </i>
    </div>
  </div>

  <div class="flow">
    <div v-for="g in groups" :key="g.dateLabel" class="group">
      <div class="group-date">{{ g.dateLabel }}</div>
      <div
        v-for="(e, i) in g.items"
        :key="e.title"
        class="ev"
        :class="{ 'ev--on': step >= 1 && g.dateLabel === '今天' && i === 0 }"
      >
        <i class="ev-logo" :class="`ev-logo--${e.tone}`">{{ e.word }}</i>
        <div class="ev-main">
          <div class="ev-top">
            <i class="tag" :class="`tag--${e.tone}`">{{ e.tag }}</i>
            <em class="ev-brand">{{ e.brand }}</em>
            <span class="ev-time">{{ e.time }}</span>
            <i
              class="pri"
              :class="{ 'pri--high': e.priority === '高优先级' }"
              >{{ e.priority }}</i
            >
          </div>
          <div class="ev-title">{{ e.title }}</div>
          <div class="ev-desc">{{ e.desc }}</div>
        </div>
        <div class="ev-side">AI {{ e.confidence }}%</div>
      </div>
    </div>
  </div>

  <!-- 详情抽屉 -->
  <div class="scrim" :class="{ 'scrim--in': step >= 2 }" />
  <aside class="drawer" :class="{ 'drawer--in': step >= 2 }">
    <div class="drawer-head">
      <i class="ev-logo ev-logo--price">N</i>
      <div class="drawer-head-main">
        <div class="drawer-title">Notion AI 团队版月付下调 15%</div>
        <div class="drawer-sub">notion.so · 抓取于 2026-09-19 09:05</div>
      </div>
      <el-icon class="drawer-close"><Close /></el-icon>
    </div>

    <div class="drawer-block">
      <div class="block-label">来源页面</div>
      <div class="chips">
        <i v-for="p in foundPages" :key="p" class="chip">
          <el-icon><Document /></el-icon>{{ p }}
        </i>
      </div>
    </div>

    <div class="drawer-block">
      <div class="block-label">变化原文</div>
      <div class="diff">
        <div class="diff-row diff-row--del">
          <span class="diff-sign">-</span>
          <span>Teams<span class="diff-mark">$18</span>/ 席位 / 月</span>
        </div>
        <div class="diff-row diff-row--add">
          <span class="diff-sign">+</span>
          <span>Teams<span class="diff-mark">$15.3</span>/ 席位 / 月</span>
        </div>
      </div>
    </div>

    <div class="drawer-block">
      <div class="block-label">AI 摘要</div>
      <p class="para">
        Notion 将 Teams 档位月付价格由 $18 下调至 $15.3，降幅约 15%；年付价格未变化。
      </p>
    </div>

    <div class="drawer-block insight" :class="{ 'insight--on': step >= 3 }">
      <div class="block-label block-label--accent">AI 影响判断</div>
      <p class="para">
        直接影响个人与 10 人以内小团队的选型比价：同价位区间内 Notion 的性价比优势被放大，
        可能挤压同类协作文档工具的入门转化。建议关注其是否在后续版本中对
        AI 用量额度做相应收紧，以判断是获客策略还是长期定价下探。
      </p>
    </div>

    <div class="drawer-foot">
      <i class="btn btn--ghost">查看历史快照</i>
      <i class="btn">
        <span>去官网核对</span>
        <el-icon><ArrowRight /></el-icon>
      </i>
    </div>
  </aside>
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
.filters {
  display: flex;
  gap: 7px;
}
.fchip {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  height: 30px;
  padding: 0 12px;
  border-radius: 11px;
  font-size: 12.5px;
  font-style: normal;
  color: var(--app-text-color-secondary);
  background: color-mix(in oklab, var(--app-color-blue) 6%, transparent);
  border: 2px solid transparent;
}
.fchip b {
  font-weight: 600;
}
.fchip--on {
  font-weight: 600;
  color: var(--app-color-blue);
  background: color-mix(in oklab, var(--app-color-blue) 13%, transparent);
  border-color: color-mix(in oklab, var(--app-color-blue) 34%, transparent);
}

/* ---------- 情报流 ---------- */
.flow {
  flex: 1;
  min-height: 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.group {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.group-date {
  font-size: 12.5px;
  font-weight: 600;
  color: var(--app-text-color-secondary);
}
.ev {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 13px 15px;
  border-radius: 16px;
  background: color-mix(in oklab, var(--app-color-white) 88%, var(--app-color-blue));
  border: 2px solid color-mix(in oklab, var(--app-color-blue) 13%, transparent);
  transition: border-color 0.45s ease, box-shadow 0.45s ease,
    background-color 0.45s ease;
}
.ev--on {
  background: color-mix(in oklab, var(--app-color-blue) 8%, var(--app-color-white));
  border-color: color-mix(in oklab, var(--app-color-blue) 50%, transparent);
  box-shadow: 0 0 0 4px color-mix(in oklab, var(--app-color-blue) 15%, transparent);
}
.ev-logo {
  flex: 0 0 auto;
  width: 34px;
  height: 34px;
  border-radius: 11px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 15px;
  font-style: normal;
  font-weight: 600;
  color: var(--app-color-white);
  background: var(--app-color-blue);
}
.ev-logo--feat {
  background: var(--app-color-blue);
}
.ev-logo--price {
  background: var(--app-color-red);
}
.ev-logo--content {
  background: var(--app-color-purple);
}
.ev-main {
  flex: 1;
  min-width: 0;
}
.ev-top {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 5px;
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
.tag--feat {
  color: var(--app-color-blue);
  background: color-mix(in oklab, var(--app-color-blue) 13%, transparent);
}
.tag--price {
  color: var(--app-color-red);
  background: color-mix(in oklab, var(--app-color-red) 13%, transparent);
}
.tag--content {
  color: var(--app-color-purple);
  background: color-mix(in oklab, var(--app-color-purple) 13%, transparent);
}
.ev-brand {
  font-style: normal;
  font-size: 12.5px;
  font-weight: 600;
  color: var(--app-text-color-secondary);
}
.ev-time {
  font-size: 12px;
  color: var(--app-text-color-placeholder);
}
.pri {
  font-style: normal;
  font-size: 11px;
  padding: 1px 7px;
  border-radius: 6px;
  color: var(--app-text-color-secondary);
  border: 1.5px solid color-mix(in oklab, var(--app-color-black) 16%, transparent);
}
.pri--high {
  color: var(--app-color-red);
  border-color: color-mix(in oklab, var(--app-color-red) 40%, transparent);
}
.ev-title {
  font-size: 14.5px;
  font-weight: 600;
}
.ev-desc {
  margin-top: 3px;
  font-size: 12.5px;
  line-height: 1.5;
  color: var(--app-text-color-secondary);
}
.ev-side {
  flex: 0 0 auto;
  font-size: 11.5px;
  align-self: center;
  padding: 3px 9px;
  border-radius: 9px;
  color: var(--app-color-purple);
  background: color-mix(in oklab, var(--app-color-purple) 11%, transparent);
}

/* ---------- 抽屉 ---------- */
.scrim {
  position: absolute;
  inset: 0;
  background: color-mix(in oklab, var(--app-color-black) 14%, transparent);
  opacity: 0;
  pointer-events: none;
  transition: opacity 0.5s ease;
}
.scrim--in {
  opacity: 1;
}
.drawer {
  position: absolute;
  top: 0;
  right: 0;
  bottom: 0;
  width: 450px;
  padding: 20px 22px;
  display: flex;
  flex-direction: column;
  gap: 15px;
  overflow: hidden;
  background: var(--app-color-white);
  border-left: 2.5px solid color-mix(in oklab, var(--app-color-blue) 32%, transparent);
  box-shadow: -14px 0 38px color-mix(in oklab, var(--app-color-blue) 20%, transparent);
  transform: translateX(102%);
  transition: transform 0.6s cubic-bezier(0.22, 1, 0.36, 1);
}
.drawer--in {
  transform: translateX(0);
}
.drawer-head {
  display: flex;
  align-items: flex-start;
  gap: 11px;
}
.drawer-head-main {
  flex: 1;
  min-width: 0;
}
.drawer-title {
  font-size: 16px;
  font-weight: 600;
  line-height: 1.35;
}
.drawer-sub {
  margin-top: 4px;
  font-size: 12px;
  color: var(--app-text-color-placeholder);
}
.drawer-close {
  flex: 0 0 auto;
  color: var(--app-text-color-placeholder);
}
.drawer-block {
  display: flex;
  flex-direction: column;
  gap: 7px;
}
.block-label {
  font-size: 12.5px;
  font-weight: 600;
  color: var(--app-text-color-secondary);
}
.block-label--accent {
  color: var(--app-color-purple);
}
.chips {
  display: flex;
  gap: 7px;
}
.chip {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  height: 28px;
  padding: 0 11px;
  border-radius: 9px;
  font-size: 12px;
  font-style: normal;
  color: var(--app-text-color-secondary);
  background: color-mix(in oklab, var(--app-color-blue) 8%, transparent);
  border: 1.5px solid color-mix(in oklab, var(--app-color-blue) 16%, transparent);
}
.diff {
  border-radius: 12px;
  overflow: hidden;
  border: 2px solid color-mix(in oklab, var(--app-color-blue) 15%, transparent);
}
.diff-row {
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 9px 12px;
  font-size: 13px;
  font-family: var(--font-mono, ui-monospace, monospace);
}
.diff-row--del {
  color: var(--app-color-red);
  background: color-mix(in oklab, var(--app-color-red) 9%, transparent);
}
.diff-row--add {
  color: var(--app-color-green);
  background: color-mix(in oklab, var(--app-color-green) 11%, transparent);
}
.diff-sign {
  font-weight: 600;
}
.diff-mark {
  margin: 0 4px;
  padding: 1px 5px;
  border-radius: 5px;
  font-weight: 600;
  background: color-mix(in oklab, currentColor 18%, transparent);
}
.para {
  margin: 0;
  font-size: 13px;
  line-height: 1.65;
  color: var(--app-text-color-regular);
}
.insight {
  padding: 13px 15px;
  border-radius: 14px;
  background: color-mix(in oklab, var(--app-color-purple) 7%, transparent);
  border: 2px solid transparent;
  transition: border-color 0.5s ease, box-shadow 0.5s ease;
}
.insight--on {
  border-color: color-mix(in oklab, var(--app-color-purple) 42%, transparent);
  box-shadow: 0 0 0 4px color-mix(in oklab, var(--app-color-purple) 13%, transparent);
}
.drawer-foot {
  margin-top: auto;
  display: flex;
  gap: 10px;
  justify-content: flex-end;
}
.btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 36px;
  padding: 0 15px;
  border-radius: 12px;
  font-size: 13.5px;
  font-style: normal;
  font-weight: 600;
  color: var(--app-color-white);
  background: var(--app-color-blue);
  border: 2px solid color-mix(in oklab, var(--app-color-blue) 70%, var(--app-color-black));
}
.btn--ghost {
  color: var(--app-text-color-secondary);
  background: transparent;
  border-color: color-mix(in oklab, var(--app-color-black) 16%, transparent);
}
</style>
