<script setup lang="ts">
/**
 * 第一幕：竞品管理 —— 把要盯的竞品加进来
 *
 * 纯展示组件：不请求接口、不读 store，数据全部写死在这里。
 * step 由 DemoPlayer 的时间轴驱动，每步点亮一个区域。
 */
import { Plus, MagicStick, Check } from "@element-plus/icons-vue";

defineProps<{ step: number }>();

const rows = [
  {
    name: "Linear",
    domain: "linear.app",
    category: "研发工具",
    pages: ["首页", "更新日志", "博客"],
    extra: 0,
    freq: "每 6 小时",
    changes: 21,
    on: true,
  },
  {
    name: "Notion",
    domain: "notion.so",
    category: "SaaS工具",
    pages: ["首页", "定价页", "更新日志"],
    extra: 2,
    freq: "每天",
    changes: 12,
    on: true,
  },
  {
    name: "Figma",
    domain: "figma.com",
    category: "设计工具",
    pages: ["首页", "定价页"],
    extra: 1,
    freq: "每天",
    changes: 8,
    on: true,
  },
  {
    name: "Vercel",
    domain: "vercel.com",
    category: "云服务",
    pages: ["首页", "定价页"],
    extra: 0,
    freq: "每天",
    changes: 3,
    on: false,
  },
];

const found = [
  { label: "定价页", url: "/pricing" },
  { label: "更新日志", url: "/changelog" },
  { label: "博客", url: "/blog" },
];
</script>

<template>
  <div class="head">
    <div>
      <div class="h1">竞品管理</div>
      <div class="h2">共 4 个竞品 · 11 个监控页面 · 下次抓取 明天 08:00</div>
    </div>
    <div class="btn" :class="{ 'btn--on': step === 0 }">
      <el-icon><Plus /></el-icon>
      <span>新增竞品</span>
    </div>
  </div>

  <div class="card table">
    <div class="tr tr--head">
      <span class="td td--name">竞品</span>
      <span class="td td--cat">分类</span>
      <span class="td td--pages">监控页面</span>
      <span class="td td--freq">频率</span>
      <span class="td td--chg">变化</span>
      <span class="td td--st">状态</span>
    </div>
    <div v-for="r in rows" :key="r.name" class="tr">
      <span class="td td--name">
        <i class="logo">{{ r.name.slice(0, 1) }}</i>
        <span class="name-col">
          <em class="name">{{ r.name }}</em>
          <em class="domain">{{ r.domain }}</em>
        </span>
      </span>
      <span class="td td--cat"><i class="tag tag--soft">{{ r.category }}</i></span>
      <span class="td td--pages">
        <i v-for="p in r.pages" :key="p" class="tag">{{ p }}</i>
        <i v-if="r.extra" class="tag tag--more">+{{ r.extra }}</i>
      </span>
      <span class="td td--freq">{{ r.freq }}</span>
      <span class="td td--chg">{{ r.changes }} 条</span>
      <span class="td td--st">
        <i class="dot" :class="{ 'dot--off': !r.on }" />
        {{ r.on ? "监控中" : "已暂停" }}
      </span>
    </div>
  </div>

  <!-- 新增竞品弹窗 -->
  <div class="dlg" :class="{ 'dlg--in': step >= 1 }">
    <div class="dlg-title">
      <el-icon><Plus /></el-icon>
      <span>新增竞品</span>
    </div>

    <div class="field">
      <label>竞品名称</label>
      <div class="input" :class="{ 'input--filled': step >= 1 }">
        <span v-if="step >= 1">Notion</span>
        <span v-else class="ph">例如：Notion</span>
      </div>
    </div>

    <div class="field">
      <label>官网地址</label>
      <div class="input input--with-btn" :class="{ 'input--filled': step >= 2 }">
        <span v-if="step >= 2">https://notion.so</span>
        <span v-else class="ph">https://</span>
        <i class="input-btn"><el-icon><MagicStick /></el-icon>自动寻找页面</i>
      </div>
    </div>

    <div class="field">
      <label>找到的监控页面</label>
      <div class="chips">
        <i
          v-for="f in found"
          :key="f.label"
          class="chip"
          :class="{ 'chip--in': step >= 2 }"
        >
          <el-icon><Check /></el-icon>
          <span class="chip-label">{{ f.label }}</span>
          <span class="chip-url">{{ f.url }}</span>
        </i>
      </div>
    </div>

    <div class="field">
      <label>监控频率</label>
      <div class="radios">
        <i class="radio" :class="{ 'radio--on': step >= 3 }">每天 08:00</i>
        <i class="radio">每 6 小时</i>
        <i class="radio">每周</i>
      </div>
    </div>

    <div class="dlg-foot">
      <i class="btn btn--ghost">取消</i>
      <i class="btn" :class="{ 'btn--on': step >= 3 }">保存并开始监控</i>
    </div>
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
  background: var(--app-color-blue);
  border: 2px solid color-mix(in oklab, var(--app-color-blue) 70%, var(--app-color-black));
  transition: box-shadow 0.4s ease, transform 0.4s ease;
}
.btn--ghost {
  color: var(--app-text-color-secondary);
  background: transparent;
  border-color: color-mix(in oklab, var(--app-color-black) 16%, transparent);
}
.btn--on {
  transform: translateY(-2px);
  box-shadow: 0 0 0 4px color-mix(in oklab, var(--app-color-blue) 26%, transparent);
}

.card {
  border-radius: 16px;
  background: color-mix(in oklab, var(--app-color-white) 88%, var(--app-color-blue));
  border: 2px solid color-mix(in oklab, var(--app-color-blue) 14%, transparent);
}

/* ---------- 表格 ---------- */
.table {
  flex: 1;
  min-height: 0;
  padding: 6px 14px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.tr {
  display: flex;
  align-items: center;
  padding: 13px 4px;
  border-bottom: 1.5px dashed color-mix(in oklab, var(--app-color-blue) 16%, transparent);
}
.tr:last-child {
  border-bottom: none;
}
.tr--head {
  font-size: 12.5px;
  font-weight: 600;
  color: var(--app-text-color-secondary);
  padding: 11px 4px;
  border-bottom: 2px solid color-mix(in oklab, var(--app-color-blue) 20%, transparent);
}
.td {
  display: flex;
  align-items: center;
  font-size: 13.5px;
}
.td--name {
  width: 190px;
  gap: 10px;
}
.td--cat {
  width: 110px;
}
.td--pages {
  flex: 1;
  min-width: 0;
  gap: 6px;
}
.td--freq {
  width: 92px;
}
.td--chg {
  width: 74px;
}
.td--st {
  width: 84px;
  gap: 6px;
}
.logo {
  flex: 0 0 auto;
  width: 30px;
  height: 30px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  font-style: normal;
  font-weight: 600;
  color: var(--app-color-white);
  background: var(--app-color-purple);
}
.name-col {
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.name {
  font-style: normal;
  font-weight: 600;
}
.domain {
  font-style: normal;
  font-size: 11.5px;
  color: var(--app-text-color-placeholder);
}
.tag {
  display: inline-flex;
  align-items: center;
  height: 22px;
  padding: 0 9px;
  border-radius: 8px;
  font-size: 11.5px;
  font-style: normal;
  color: var(--app-color-blue);
  background: color-mix(in oklab, var(--app-color-blue) 10%, transparent);
  border: 1.5px solid color-mix(in oklab, var(--app-color-blue) 20%, transparent);
}
.tag--soft {
  color: var(--app-color-purple);
  background: color-mix(in oklab, var(--app-color-purple) 10%, transparent);
  border-color: color-mix(in oklab, var(--app-color-purple) 20%, transparent);
}
.tag--more {
  color: var(--app-text-color-secondary);
  background: transparent;
  border-style: dashed;
  border-color: color-mix(in oklab, var(--app-color-black) 18%, transparent);
}
.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--app-color-green);
}
.dot--off {
  background: var(--app-text-color-placeholder);
}

/* ---------- 弹窗 ---------- */
.dlg {
  position: absolute;
  left: 50%;
  top: 50%;
  width: 520px;
  padding: 20px 22px;
  border-radius: 20px;
  background: var(--app-color-white);
  border: 2.5px solid color-mix(in oklab, var(--app-color-blue) 40%, transparent);
  box-shadow: 0 18px 46px color-mix(in oklab, var(--app-color-blue) 30%, transparent);
  display: flex;
  flex-direction: column;
  gap: 13px;
  opacity: 0;
  transform: translate(-50%, -50%) scale(0.94);
  transition: opacity 0.5s ease, transform 0.5s cubic-bezier(0.34, 1.3, 0.64, 1);
}
.dlg--in {
  opacity: 1;
  transform: translate(-50%, -50%) scale(1);
}
.dlg-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 17px;
  font-weight: 600;
  color: var(--app-color-blue);
}
.field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.field label {
  font-size: 12.5px;
  font-weight: 600;
  color: var(--app-text-color-secondary);
}
.input {
  height: 40px;
  padding: 0 13px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  font-size: 14px;
  background: color-mix(in oklab, var(--app-color-blue) 5%, transparent);
  border: 2px solid color-mix(in oklab, var(--app-color-blue) 14%, transparent);
  transition: border-color 0.4s ease, background-color 0.4s ease;
}
.input--filled {
  border-color: color-mix(in oklab, var(--app-color-blue) 45%, transparent);
  background: color-mix(in oklab, var(--app-color-blue) 9%, transparent);
}
.ph {
  color: var(--app-text-color-placeholder);
}
.input--with-btn {
  padding-right: 6px;
  gap: 8px;
  justify-content: space-between;
}
.input-btn {
  flex: 0 0 auto;
  display: inline-flex;
  align-items: center;
  gap: 5px;
  height: 28px;
  padding: 0 10px;
  border-radius: 9px;
  font-size: 12.5px;
  font-style: normal;
  color: var(--app-color-blue);
  background: color-mix(in oklab, var(--app-color-blue) 12%, transparent);
}
.chips {
  display: flex;
  gap: 8px;
}
.chip {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  height: 32px;
  padding: 0 11px;
  border-radius: 11px;
  font-size: 12.5px;
  font-style: normal;
  color: var(--app-color-green);
  background: color-mix(in oklab, var(--app-color-green) 11%, transparent);
  border: 2px solid color-mix(in oklab, var(--app-color-green) 28%, transparent);
  opacity: 0;
  transform: translateY(6px);
  transition: opacity 0.4s ease, transform 0.4s ease;
}
.chip--in {
  opacity: 1;
  transform: translateY(0);
}
.chip:nth-child(1) {
  transition-delay: 0s;
}
.chip:nth-child(2) {
  transition-delay: 0.12s;
}
.chip:nth-child(3) {
  transition-delay: 0.24s;
}
.chip-label {
  font-weight: 600;
}
.chip-url {
  color: var(--app-text-color-placeholder);
}
.radios {
  display: flex;
  gap: 8px;
}
.radio {
  height: 34px;
  padding: 0 13px;
  border-radius: 11px;
  display: flex;
  align-items: center;
  font-size: 13px;
  font-style: normal;
  color: var(--app-text-color-secondary);
  background: color-mix(in oklab, var(--app-color-blue) 5%, transparent);
  border: 2px solid color-mix(in oklab, var(--app-color-blue) 14%, transparent);
  transition: all 0.4s ease;
}
.radio--on {
  font-weight: 600;
  color: var(--app-color-blue);
  background: color-mix(in oklab, var(--app-color-blue) 14%, transparent);
  border-color: color-mix(in oklab, var(--app-color-blue) 46%, transparent);
}
.dlg-foot {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 2px;
}
.dlg-foot .btn {
  font-style: normal;
  cursor: default;
}
</style>
