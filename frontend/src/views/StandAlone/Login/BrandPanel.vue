<script setup lang="ts">
import {
  Clock,
  MagicStick,
  TrendCharts,
  Document,
  TopRight,
} from "@element-plus/icons-vue";
import RadarCanvas from "./RadarCanvas.vue";

/** 浮动情报卡片：position 对应样式里的四个方位 */
const cards = [
  {
    name: "OpenAI",
    event: "价格调整",
    abbr: "O",
    color: "#10a37f",
    position: "card-tl",
  },
  {
    name: "Claude",
    event: "新功能发布",
    abbr: "AI",
    color: "#d97757",
    position: "card-tr",
  },
  {
    name: "Midjourney",
    event: "产品更新",
    abbr: "M",
    color: "#6366f1",
    position: "card-bl",
  },
  {
    name: "Anthropic",
    event: "模型升级",
    abbr: "A",
    color: "#8b5cf6",
    position: "card-br",
  },
];

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
          v-for="card in cards"
          :key="card.name"
          class="float-card"
          :class="card.position"
        >
          <span class="float-card-logo" :style="{ background: card.color }">
            {{ card.abbr }}
          </span>
          <div class="float-card-text">
            <span class="float-card-name">{{ card.name }}</span>
            <span class="float-card-event">
              {{ card.event }}
              <el-icon><TopRight /></el-icon>
            </span>
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
  display: flex;
  align-items: center;
  gap: 0.5vw;
  padding: 1vh 1vw;
  border-radius: 1vmax;
  background: color-mix(in oklch, var(--app-color-white) 5%, transparent);
  border: 1px solid color-mix(in oklch, var(--app-color-white) 30%, transparent);
  backdrop-filter: blur(4px);
  animation: floatY 4s ease-in-out infinite;
}
.card-tl {
  left: 10%;
  top: 5%;
  animation-delay: 0s;
}
.card-tr {
  right: 15%;
  top: 20%;
  animation-delay: 1s;
}
.card-bl {
  left: 5%;
  bottom: 20%;
  animation-delay: 2s;
}
.card-br {
  right: 5%;
  bottom: 10%;
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
  width: 3vmax;
  height: 3vmax;
  border-radius: 1vmax;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1vmax;
  font-weight: bold;
}
.float-card-text {
  display: flex;
  flex-direction: column;
}
.float-card-name {
  font-size: 1.5vmax;
  font-weight: bold;
}
.float-card-event {
  display: flex;
  align-items: center;
  gap: 0.2vw;
  font-size: 1vmax;
  opacity: 0.7;
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
