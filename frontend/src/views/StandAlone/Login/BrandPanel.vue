<script setup lang="ts">
import { onBeforeUnmount, onMounted, reactive } from "vue";
import {
  Clock,
  MagicStick,
  TrendCharts,
  Document,
} from "@element-plus/icons-vue";
import RadarCanvas from "./RadarCanvas.vue";

/**
 * 演示情报流：跨品类代表竞品动态（与 seed_mock_data 一致），轮流喂给四张悬浮卡当作「直播」。
 * 图标用「事件类型」矢量图标（新功能/价格调整/舆论动态），竞品身份体现在文字里的竞品名，
 * 避免依赖真实 favicon（Notion/Figma 等 SPA 会加载失败）或复刻官方商标。
 */
const feed = [
  { name: "飞书", color: "#3370ff", type: "新功能", text: "多维表格接入 AI 智能助手" },
  { name: "钉钉", color: "#1677ff", type: "价格调整", text: "下调基础版团队人数限制" },
  { name: "腾讯会议", color: "#0052d9", type: "新功能", text: "上线 AI 实时字幕翻译" },
  { name: "Notion", color: "#141414", type: "新功能", text: "发布全新 AI 工作区" },
  { name: "Asana", color: "#f06a6a", type: "新功能", text: "上线 AI 项目规划助手" },
  { name: "Figma", color: "#a259ff", type: "新功能", text: "发布 AI 设计生成" },
  { name: "GitHub", color: "#24292f", type: "新功能", text: "Copilot 新版本发布" },
  { name: "企业微信", color: "#07c160", type: "新功能", text: "打通视频号直播带货" },
  { name: "腾讯会议", color: "#0052d9", type: "价格调整", text: "调整个人版收费策略" },
  { name: "Notion", color: "#141414", type: "价格调整", text: "商业版席位定价上调" },
];

/** 竞品 → 原创抽象线描符号（功能隐喻，非官方商标；每个竞品唯一、风格统一、互不重复） */
const ICONS: Record<string, string> = {
  飞书: `<path d="M4 4h16v10H9l-5 4z" />`,
  钉钉: `<path d="M4 13l5 5 11-12" />`,
  企业微信: `<circle cx="6" cy="12" r="3" /><circle cx="18" cy="12" r="3" /><path d="M9 12h6" />`,
  腾讯会议: `<rect x="3" y="6" width="13" height="12" rx="2" /><path d="M16 10l5-3v10l-5-3z" />`,
  Notion: `<path d="M6 3h9l4 4v14H6z" /><path d="M9 11h6M9 15h6M9 19h3" />`,
  Asana: `<path d="M6 5v14M12 5v14M18 5v14" />`,
  Figma: `<circle cx="12" cy="7" r="3.5" /><circle cx="12" cy="16" r="3.5" />`,
  GitHub: `<path d="M9 6l-5 6 5 6M15 6l5 6-5 6" />`,
};
const logoIcon = (name: string) => ICONS[name] ?? ICONS.飞书;

/** 四张卡片 = 四个槽位，各自持有一条动态；游标轮流更新槽位模拟「直播」 */
const positionClasses = ["card-tl", "card-tr", "card-bl", "card-br"];
const slots = reactive(
  Array.from({ length: 4 }, (_, i) => ({ ...feed[i % feed.length] })),
);
let feedIndex = 4; // 下一条待展示的 feed 下标（前 4 条已用于初始化 slots）
let autoSlot = 0; // 定时器下一次自动更新的槽位
let timer: number | undefined;

/** 从 feed 取「下一条」并推进内容游标 */
function takeNext() {
  const item = { ...feed[feedIndex % feed.length] };
  feedIndex += 1;
  return item;
}

/** 定时器自动轮播：按 0→1→2→3 轮流更新槽位 */
function nextFeed() {
  slots[autoSlot] = takeNext();
  autoSlot = (autoSlot + 1) % slots.length;
}

/** 点击某张卡片：只切换被点的那张，并重置自动轮播计时，避免点完立刻又被定时器切走 */
function advanceSlot(index: number) {
  slots[index] = takeNext();
  if (timer !== undefined) window.clearInterval(timer);
  timer = window.setInterval(nextFeed, 4000);
}

onMounted(() => {
  timer = window.setInterval(nextFeed, 4000);
});
onBeforeUnmount(() => {
  if (timer !== undefined) window.clearInterval(timer);
});

/** 底部能力标签 */
const features = [
  { icon: Clock, title: "7×24 小时监控", desc: "不间断捕捉变化" },
  { icon: MagicStick, title: "AI 智能分析", desc: "深度提炼关键信息" },
  { icon: TrendCharts, title: "趋势洞察", desc: "发现市场机会" },
  { icon: Document, title: "智能报告", desc: "自动生成周报" },
];
</script>

<template>
  <aside class="brand-panel">
    <!-- 雷达背景 -->
    <div class="radar-bg">
      <RadarCanvas />
    </div>

    <!-- 品牌内容区 -->
    <div class="brand-content">
      <!-- 主标题 + 副标题 -->
      <div class="brand-header">
        <div class="brand-title">
          捕捉变化，<span class="highlight">洞察先机</span>
        </div>
        <div class="brand-subtitle">
          实时监控市场动态 · 智能分析竞品变化 · 助力决策领先一步
        </div>
      </div>

      <!-- 雷达视觉区：Canvas + 浮动卡片 -->
      <div class="brand-visual">
        <div
          v-for="(card, i) in slots"
          :key="i"
          class="float-card"
          :class="positionClasses[i]"
          @click="advanceSlot(i)"
        >
          <span class="float-card-logo" :style="{ background: card.color }">
            <svg
              class="float-card-svg"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="1.8"
              stroke-linecap="round"
              stroke-linejoin="round"
              v-html="logoIcon(card.name)"
            />
          </span>
          <div class="float-card-text">
            <span class="float-card-type">{{ card.name }} · {{ card.type }}</span>
            <Transition name="feed-swap" mode="out-in">
              <span :key="card.text" class="float-card-msg">
                {{ card.text }}
              </span>
            </Transition>
          </div>
        </div>
      </div>

      <!-- 底部能力标签 -->
      <footer class="brand-features">
        <div v-for="f in features" :key="f.title" class="brand-feature">
          <span class="brand-feature-icon">
            <el-icon><component :is="f.icon" /></el-icon>
          </span>
          <span class="brand-feature-title">{{ f.title }}</span>
          <span class="brand-feature-desc">{{ f.desc }}</span>
        </div>
      </footer>
    </div>
  </aside>
</template>

<style scoped>
/* 品牌面板：左侧固定宽度，右侧撑开 */
.brand-panel {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 2vh;
  color: var(--app-color-white);
  height: 100%;
}
/* 雷达背景 */
.radar-bg {
  position: absolute;
  inset: 0;
  z-index: 0;
}
/* 内容层：相对定位，z-index 上层，padding 控制安全区 */
.brand-content {
  height: 100%;
  position: relative;
  z-index: 1;
  display: flex;
  flex-direction: column;
  gap: 2vh;
  padding: 2vh 2vw; /* 内容不贴边，给雷达留出呼吸空间 */
}

.brand-header {
  margin: 0;
  line-height: 1.4;
}
.brand-title {
  font-size: 3vmax;
  color: var(--app-color-blue-dark-2);
}
/* 渐变高亮文字 */
.brand-title .highlight {
  background: linear-gradient(
    90deg,
    var(--app-color-purple),
    var(--app-color-blue-dark-3)
  );
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
}
.brand-subtitle {
  font-size: 2vmax;
  color: var(--app-color-blue-dark-2);
  opacity: 0.65;
}

/* 雷达视觉区：flex 撑开剩余高度，卡片相对它定位 */
.brand-visual {
  position: relative;
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
}
/* 浮动情报卡片 */
.float-card {
  position: absolute;
  max-width: 46%;
  display: flex;
  align-items: center;
  gap: 0.5vw;
  padding: 1vh 1vw;
  border-radius: 1vmax;
  background: color-mix(in oklch, var(--app-color-white) 5%, transparent);
  border: 1px solid color-mix(in oklch, var(--app-color-white) 30%, transparent);
  backdrop-filter: blur(4px);
  animation: floatY 4s ease-in-out infinite;
  cursor: pointer;
  transition: background 0.2s ease, border-color 0.2s ease;
}
.float-card:hover {
  background: color-mix(in oklch, var(--app-color-white) 10%, transparent);
  border-color: color-mix(in oklch, var(--app-color-white) 50%, transparent);
}
.card-tl {
  left: 3%;
  top: 14%;
  animation-delay: 0s;
}
.card-tr {
  right: 3%;
  top: 30%;
  animation-delay: 1s;
}
.card-bl {
  left: 6%;
  bottom: 18%;
  animation-delay: 2s;
}
.card-br {
  right: 6%;
  bottom: 8%;
  animation-delay: 3s;
}
@keyframes floatY {
  0%,
  100% {
    transform: translateY(0);
  }
  50% {
    transform: translateY(-1.2vh);
  }
}
.float-card-logo {
  width: 2.4vmax;
  height: 2.4vmax;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  flex: none;
  box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.22);
}
.float-card-svg {
  width: 1.5vmax;
  height: 1.5vmax;
}
.float-card-text {
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.float-card-type {
  font-size: 1vmax;
  font-weight: bold;
  color: color-mix(in oklch, var(--app-color-white) 85%, transparent);
}
.float-card-msg {
  font-size: 1.05vmax;
  opacity: 0.72;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
/* 情报切换过渡：旧内容淡出 + 新内容淡入上滑 */
.feed-swap-enter-active {
  transition: all 0.45s ease;
}
.feed-swap-enter-from {
  opacity: 0;
  transform: translateY(8px);
}
.feed-swap-leave-active {
  transition: opacity 0.2s ease;
}
.feed-swap-leave-to {
  opacity: 0;
}

/* 底部能力标签 */
.brand-features {
  display: flex;
  justify-content: space-between;
}
.brand-feature {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.5vh;
  text-align: center;
}
.brand-feature-icon {
  width: 3vmax;
  height: 3vmax;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1.5vmax;
  color: var(--app-color-purple);
  background: color-mix(in oklch, var(--app-color-white) 30%, transparent);
}
.brand-feature-title {
  font-size: 1.2vmax;
  font-weight: bold;
}
.brand-feature-desc {
  font-size: 1vmax;
  opacity: 0.6;
}
</style>
