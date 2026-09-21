<script setup lang="ts">
import Logo from "@/components/Logo.vue";
import DemoPlayer from "@/components/DemoPlayer/DemoPlayer.vue";
import { computed, ref, onMounted, onUnmounted } from "vue";
import { Star } from "@element-plus/icons-vue";

const activeId = ref("home");
const navItems = ["home", "preview", "features", "workflow"];
let observer: IntersectionObserver;

// 页脚在页面最底部，进不了下面那条高亮判定带（-40% / -55%）：
// 单独看"是否已滚到底"来决定「关于」的高亮
const atBottom = ref(false);
function updateAtBottom() {
  const el = document.documentElement;
  atBottom.value = el.scrollHeight - el.scrollTop - el.clientHeight <= 2;
}

// 刚点过的导航项：先锁定它。否则会出现"点工作流程却高亮关于"——
// 工作流程已经是最后一个区块，页脚又不矮，锚点滚到位时页面已经到底了。
const clickedId = ref("");
function onNavClick(id: string) {
  clickedId.value = id;
}
/** 用户自己滚动（滚轮 / 触摸 / 键盘）时解除锁定，交还给区块观察 */
function releaseClickLock() {
  clickedId.value = "";
}

/** 当前高亮的导航项：优先"刚点的那项"，其次滚到底＝关于，最后是区块观察结果 */
const activeNav = computed(() => {
  if (clickedId.value) return clickedId.value;
  return atBottom.value ? "footer" : activeId.value;
});

// 监听滚动，根据滚动位置设置 activeId
onMounted(() => {
  const sections = navItems
    .map((id) => document.getElementById(id))
    .filter(Boolean) as HTMLElement[];
  observer = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          activeId.value = entry.target.id;
        }
      });
    },
    { rootMargin: "-40% 0px -55% 0px", threshold: 0 },
  );
  sections.forEach((s) => observer.observe(s));
  updateAtBottom();
  window.addEventListener("scroll", updateAtBottom, { passive: true });
  // 注意只监听用户主动滚动：锚点跳转也会触发 scroll，会把刚点的锁定冲掉
  window.addEventListener("wheel", releaseClickLock, { passive: true });
  window.addEventListener("touchstart", releaseClickLock, { passive: true });
  window.addEventListener("keydown", releaseClickLock);
});
onUnmounted(() => {
  observer?.disconnect();
  window.removeEventListener("scroll", updateAtBottom);
  window.removeEventListener("wheel", releaseClickLock);
  window.removeEventListener("touchstart", releaseClickLock);
  window.removeEventListener("keydown", releaseClickLock);
});
</script>

<template>
  <!-- 导航栏 -->
  <header class="landing-header">
    <div class="landing-header-container">
      <!-- logo：点它回首页（与导航「首页」同一个锚点） -->
      <a class="landing-header-logo" href="#home">
        <Logo size="1.5em" />
        <span class="landing-header-logo-text">竞品雷达</span>
      </a>

      <!-- 导航链接 -->
      <nav class="landing-header-nav">
        <a
          href="#home"
          :class="{ active: activeNav === 'home' }"
          @click="onNavClick('home')"
          >首页</a
        >
        <a
          href="#preview"
          :class="{ active: activeNav === 'preview' }"
          @click="onNavClick('preview')"
          >产品演示</a
        >
        <a
          href="#features"
          :class="{ active: activeNav === 'features' }"
          @click="onNavClick('features')"
          >核心功能</a
        >
        <a
          href="#workflow"
          :class="{ active: activeNav === 'workflow' }"
          @click="onNavClick('workflow')"
          >工作流程</a
        >
        <!-- 关于：滚到页脚（文档 / GitHub / 法务都在那）；滚到底时它才高亮 -->
        <a
          href="#footer"
          :class="{ active: activeNav === 'footer' }"
          @click="onNavClick('footer')"
          >关于</a
        >
      </nav>

      <!-- 右边按钮 -->
      <div class="landing-header-actions">
        <el-button class="landing-header-actions-btn" type="primary"
          @click="$router.push({ name: 'Login' })">快速开始</el-button>
      </div>
    </div>
  </header>

  <!-- 产品展示页 -->
  <main class="landing-page">
    <!-- 产品内容 -->
    <section class="hero" id="home">
      <div class="hero-container">
        <!-- 标语 -->
        <div class="hero-slogan">
          <el-icon>
            <Star />
          </el-icon>
          <span>用 AI 盯住竞品的每一次公开变化</span>
        </div>
        <!-- 标题 -->
        <div class="hero-title">
          <span class="hero-highlight">竞品</span>雷达
        </div>
        <!-- 副标题 -->
        <div class="hero-subtitle">竞品官网一变，立刻知道</div>
        <!-- 产品描述 -->
        <div class="hero-description">
          持续监控竞品官网、定价页、更新日志与博客等公开页面，用快照对比找出「变了什么」，
          再由 AI 翻译成「这件事意味着什么」
        </div>
        <!-- 按钮 -->
        <div class="hero-actions">
          <el-button class="hero-actions-left" type="primary" @click="$router.push({ name: 'Login' })">开始使用</el-button>
        </div>
        <!-- 产品特性数据 -->
        <div class="hero-feature-row">
          <div class="hero-feature-item">
            <span class="hero-feature-num">10x+</span>
            <span class="hero-feature-desc">分析效率提升</span>
          </div>
          <div class="hero-feature-item">
            <span class="hero-feature-num">95%+</span>
            <span class="hero-feature-desc">关键信息识别率</span>
          </div>
          <div class="hero-feature-item">
            <span class="hero-feature-num">7×24h</span>
            <span class="hero-feature-desc">自动持续监控</span>
          </div>
        </div>
      </div>
    </section>

    <!-- 产品演示 -->
    <section class="preview" id="preview">
      <!-- 标题行 -->
      <div class="preview-head">
        <div class="preview-head-text">
          <div class="preview-head-title">产品演示</div>
          <div class="preview-head-subtitle">
            四幕动画走一遍主流程：添加竞品 → 查看情报 → 生成周报 → 读趋势
          </div>
        </div>
      </div>

      <DemoPlayer />
    </section>

    <!-- 功能特性 -->
    <section class="features" id="features">
      <!-- 功能特性标题 -->
      <div class="feature-header">
        <div class="feature-title">核心功能</div>
        <div class="feature-subtitle">
          盯住官网与公开数据源的每一次变化，把差异变成可行动的情报
        </div>
      </div>
      <!-- 功能特性卡片列表 -->
      <div class="feature-card-list">
        <!-- 卡片1：自动化监控 -->
        <div class="feature-card">
          <div class="feature-card-header">
            <span class="feature-card-header-icon icon-blue-light">
              <svg color="var(--app-color-blue)" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                <path d="M3 8V5c0-1.1.9-2 2-2h3" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"
                  stroke-linejoin="round" />
                <path d="M21 8V5c0-1.1-.9-2-2-2h-3" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"
                  stroke-linejoin="round" />
                <path d="M3 16v3c0 1.1.9 2 2 2h3" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"
                  stroke-linejoin="round" />
                <path d="M21 16v3c0 1.1-.9 2-2 2h-3" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"
                  stroke-linejoin="round" />
                <circle cx="12" cy="12" r="5" stroke="currentColor" stroke-width="1.8" />
                <circle cx="12" cy="12" r="1.8" fill="currentColor" />
              </svg>
            </span>
            <div class="feature-card-title">自动化监控</div>
          </div>
          <div class="feature-card-desc">
            7×24 小时持续监控竞品官网首页、定价页、更新日志、博客与状态页等公开页面，
            自动生成快照差异，第一时间发现变化。
          </div>
        </div>

        <!-- 卡片2：AI智能分析 -->
        <div class="feature-card">
          <div class="feature-card-header">
            <span class="feature-card-header-icon icon-purple-light">
              <svg color="var(--app-color-purple)" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                <path
                  d="M12 3c-3.5 0-6 2.5-6 5.5 0 1.2-1.2 2-1.2 3.5s1.2 2.3 1.2 3.5c0 3 2.5 5.5 6 5.5s6-2.5 6-5.5c0-1.2 1.2-2.3 1.2-3.5s-1.2-2.3-1.2-3.5c0-3-2.5-5.5-6-5.5z"
                  stroke="currentColor" stroke-width="1.8" stroke-linejoin="round" />
                <line x1="12" y1="4" x2="12" y2="20" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" />
                <circle cx="8.5" cy="7.5" r="1" fill="currentColor" />
                <circle cx="8" cy="11.5" r="1" fill="currentColor" />
                <circle cx="8.5" cy="15.5" r="1" fill="currentColor" />
                <circle cx="15.5" cy="7.5" r="1" fill="currentColor" />
                <circle cx="16" cy="11.5" r="1" fill="currentColor" />
                <circle cx="15.5" cy="15.5" r="1" fill="currentColor" />
              </svg>
            </span>
            <div class="feature-card-title">AI 智能分析</div>
          </div>
          <div class="feature-card-desc">
            用大语言模型分析页面差异，自动判断变化类型（功能 / 价格 / 内容 / 舆论），
            生成一眼就能读懂的情报摘要与影响判断。
          </div>
        </div>

        <!-- 卡片3：趋势洞察 -->
        <div class="feature-card">
          <div class="feature-card-header">
            <span class="feature-card-header-icon icon-green-light">
              <svg color="var(--app-color-green)" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                <rect x="3.5" y="14" width="5" height="7" rx="1.5" stroke="currentColor" stroke-width="1.8" />
                <rect x="9.5" y="9" width="5" height="12" rx="1.5" stroke="currentColor" stroke-width="1.8" />
                <rect x="15.5" y="4" width="5" height="17" rx="1.5" stroke="currentColor" stroke-width="1.8" />
              </svg>
            </span>
            <div class="feature-card-title">趋势洞察</div>
          </div>
          <div class="feature-card-desc">
            基于历史数据的多维度趋势分析，帮助你把握行业发展方向，发现潜在机会与风险。
          </div>
        </div>
      </div>
    </section>

    <!-- 工作流程 -->
    <section class="workflow" id="workflow">
      <!-- 工作流程标题 -->
      <div class="workflow-header">
        <div class="workflow-header-title">简单 4 步，开启智能竞品分析</div>
        <div class="workflow-header-subtitle">从配置到获取洞察，全程自动化</div>
      </div>
      <!-- 工作流程步骤 -->
      <div class="workflow-steps">
        <!-- 步骤1：添加竞品 -->
        <div class="workflow-steps-item">
          <div class="workflow-steps-icon icon-blue-lighter">
            <svg color="var(--app-color-blue-light-1)" viewBox="0 0 24 24" fill="none"
              xmlns="http://www.w3.org/2000/svg">
              <rect x="5" y="4" width="14" height="16" rx="2" stroke="currentColor" stroke-width="1.8" />
              <line x1="12" y1="8" x2="12" y2="16" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" />
              <line x1="8" y1="12" x2="16" y2="12" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" />
            </svg>
          </div>
          <div class="workflow-steps-item-title">1. 添加竞品</div>
          <div class="workflow-steps-item-desc">配置监控的竞品和目标页面</div>
        </div>

        <div class="steps-arrow">→</div>

        <!-- 步骤2：自动监控 -->
        <div class="workflow-steps-item">
          <div class="workflow-steps-icon icon-blue-light">
            <svg color="var(--app-color-blue)" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
              <rect x="3" y="6" width="14" height="12" rx="2" stroke="currentColor" stroke-width="1.8" />
              <path d="M17 9l4-2v10l-4-2" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round" />
              <rect x="7" y="10" width="3" height="3" fill="currentColor" />
            </svg>
          </div>
          <div class="workflow-steps-item-title">2. 自动监控</div>
          <div class="workflow-steps-item-desc">系统定时抓取最新信息</div>
        </div>

        <div class="steps-arrow">→</div>

        <!-- 步骤3：AI智能分析 -->
        <div class="workflow-steps-item">
          <div class="workflow-steps-icon icon-purple-light">
            <svg color="var(--app-color-purple)" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
              <circle cx="12" cy="12" r="2.5" stroke="currentColor" stroke-width="1.8" />
              <circle cx="6" cy="7" r="1.5" stroke="currentColor" stroke-width="1.8" />
              <circle cx="18" cy="7" r="1.5" stroke="currentColor" stroke-width="1.8" />
              <circle cx="6" cy="17" r="1.5" stroke="currentColor" stroke-width="1.8" />
              <circle cx="18" cy="17" r="1.5" stroke="currentColor" stroke-width="1.8" />
              <line x1="7.5" y1="8.5" x2="10" y2="10.5" stroke="currentColor" stroke-width="1.8"
                stroke-linecap="round" />
              <line x1="16.5" y1="8.5" x2="14" y2="10.5" stroke="currentColor" stroke-width="1.8"
                stroke-linecap="round" />
              <line x1="7.5" y1="15.5" x2="10" y2="13.5" stroke="currentColor" stroke-width="1.8"
                stroke-linecap="round" />
              <line x1="16.5" y1="15.5" x2="14" y2="13.5" stroke="currentColor" stroke-width="1.8"
                stroke-linecap="round" />
            </svg>
          </div>
          <div class="workflow-steps-item-title">3. AI 智能分析</div>
          <div class="workflow-steps-item-desc">大模型提炼关键信息与变化</div>
        </div>

        <div class="steps-arrow">→</div>

        <!-- 步骤4：获取情报 -->
        <div class="workflow-steps-item">
          <div class="workflow-steps-icon icon-green-light">
            <svg color="var(--app-color-green)" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
              <rect x="5" y="3" width="14" height="18" rx="2" stroke="currentColor" stroke-width="1.8" />
              <line x1="9" y1="8" x2="15" y2="8" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" />
              <line x1="9" y1="12" x2="15" y2="12" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" />
              <line x1="9" y1="16" x2="12" y2="16" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" />
            </svg>
          </div>
          <div class="workflow-steps-item-title">4. 获取情报</div>
          <div class="workflow-steps-item-desc">查看分析报告与趋势洞察</div>
        </div>
      </div>
    </section>
  </main>

  <!-- 底部导航栏：id 供顶部导航「关于」锚点跳转 -->
  <footer class="landing-footer" id="footer">
    <!-- 底部导航栏容器 -->
    <div class="landing-footer-container">
      <!-- 品牌信息 -->
      <div class="landing-footer-brand">
        <span class="landing-footer-brand-title">竞品雷达</span>
        <span class="landing-footer-brand-subtitle">让 AI 盯住竞品的每一次官网变化</span>
      </div>

      <!-- 导航链接 -->
      <nav class="landing-footer-nav">
        <!-- 产品：核心功能 / 产品演示是顶部导航已有的同页锚点，放这里纯重复，
             而且从页面底部点它们几乎不移动，故只保留真正有落点的「使用文档」 -->
        <div class="landing-footer-nav-item">
          <span class="landing-footer-nav-item-title">产品</span>
          <router-link :to="{ name: 'Help' }">使用文档</router-link>
        </div>

        <!-- 关于：只留一个 GitHub 入口，Issues 与仓库是同一个地方，不必列两条 -->
        <div class="landing-footer-nav-item">
          <span class="landing-footer-nav-item-title">关于</span>
          <a
            href="https://github.com/tsz0328/competitor-radar"
            target="_blank"
            rel="noopener noreferrer"
          >GitHub</a>
        </div>

        <!-- 法律（站内页面，用 router-link 走前端路由） -->
        <div class="landing-footer-nav-item">
          <span class="landing-footer-nav-item-title">法律</span>
          <router-link :to="{ name: 'Privacy' }">隐私政策</router-link>
          <router-link :to="{ name: 'Terms' }">服务条款</router-link>
        </div>
      </nav>

      <!-- 版权信息 -->
      <div class="landing-footer-copyright">
        <span>© 2026 竞品雷达. All rights reserved.</span>
      </div>
    </div>
  </footer>
</template>

<style scoped>
/* 按钮字号、圆角、内边距：由全局移到此页，仅本页按钮生效 */
.el-button {
  --el-font-size-base: 1.5vmax;
  --el-border-radius-base: 100vmax;
  --btn-padding-y: 1vh;
  --btn-padding-x: 1.6vw;

  height: auto;
  font-size: var(--el-font-size-base);
  border-radius: var(--el-border-radius-base);
  padding: var(--btn-padding-y) var(--btn-padding-x);
}
/* 顶部导航栏 */
.landing-header {
  position: sticky;
  top: 0;
  z-index: 100;
  background: color-mix(in oklch, var(--app-color-white) 80%, transparent);
  backdrop-filter: blur(12px);
  border-bottom: 1px solid color-mix(in oklch, var(--app-color-blue) 8%, var(--app-color-white));
}

/* 导航栏容器 */
.landing-header-container {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1vh 5vw;
}

/* logo（本身是 <a href="#home">：点它回首页，故清掉链接默认样式） */
.landing-header-logo {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 1vw;
  font-weight: bold;
  cursor: pointer;
  font-size: 2vmax;
  text-decoration: none;
  color: inherit;
  transition: color 0.2s ease, transform 0.2s ease;
}

/* 悬浮 / 点击反馈：文字变色放大，与导航链接的配色一致 */
.landing-header-logo:hover {
  color: var(--app-color-blue-light-1);
  transform: scale(1.05);
}
.landing-header-logo:active {
  color: var(--app-color-blue-dark-1);
  transform: scale(0.98);
}

/* logo 是 PNG，不吃 color：用滤镜让图标跟文字同步。
   基线必须与悬浮态写同一组滤镜函数，否则插值不连续会先闪一帧暗色 */
.landing-header-logo :deep(.logo-img) {
  filter: brightness(1) saturate(1);
  will-change: filter, transform;
  transition: filter 0.2s ease, transform 0.2s ease;
}
.landing-header-logo:hover :deep(.logo-img) {
  filter: brightness(1.12) saturate(1.25);
}
.landing-header-logo:active :deep(.logo-img) {
  filter: brightness(0.92) saturate(1.05);
  transform: scale(0.96);
}

/* 导航链接 */
.landing-header-nav {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 2vw;
  font-size: 1.5vmax;
}

/* 每一个导航 */
.landing-header-nav a {
  text-decoration: none;
  color: color-mix(in oklch, var(--app-color-black) 70%, var(--app-color-gray));
}

/* 导航hover时 */
.landing-header-nav a:hover {
  color: var(--app-color-blue-light-1);
}

/* 导航点击时 */
.landing-header-nav a:active {
  color: var(--app-color-blue-dark-1);
}

/* 滚动到对应位置时 */
.landing-header-nav a.active {
  color: var(--app-color-blue);
  font-weight: bold;
}

/* 右边按钮 */
.landing-header-actions {
  display: flex;
  align-items: center;
  justify-content: center;
}

/* 快速开始按钮 */
.landing-header-actions-btn {
  background: linear-gradient(135deg,
      var(--app-color-blue-light-2),
      var(--app-color-purple));
  box-shadow: 0 4px 16px color-mix(in oklch, var(--app-color-blue) 20%, transparent);
  transition: all 0.2s ease;
}
/* 快速开始按钮hover时 */
.landing-header-actions-btn:hover {
  background: linear-gradient(135deg,
      var(--app-color-purple-light-1),
      var(--app-color-blue-light-3));
  box-shadow: 0 6px 24px color-mix(in oklch, var(--app-color-purple) 30%, transparent);
}
/* 快速开始按钮点击时 */
.landing-header-actions-btn:active {
  background: linear-gradient(135deg,
      var(--app-color-purple),
      var(--app-color-blue-light-2));
  box-shadow: 0 2px 8px color-mix(in oklch, var(--app-color-purple) 30%, transparent);
  transform: translateY(1px);
}

/* 产品内容 */
.landing-page {
  background: linear-gradient(135deg,
      var(--app-color-purple),
      var(--app-color-white-purple));
}

.landing-page section[id] {
  scroll-margin-top: 10vh;
}

/* 主页 */
.hero {
  padding: 5vh 0;
}

/* 内层 */
.hero-container {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
}

/* 标语 */
.hero-slogan {
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1.5vmax;
  font-weight: bold;
  background-color: var(--app-color-blue-light-3);
  padding: 0.5vh 1vw;
  border-radius: 100vmax;
  gap: 1vw;
}

/* 标题 */
.hero-title {
  font-size: 5vmax;
  font-weight: bold;
}

/* 标题高亮 */
.hero-highlight {
  color: var(--el-color-primary);
}

/* 副标题 */
.hero-subtitle {
  font-size: 3vmax;
  font-weight: bold;
}

/* 产品描述 */
.hero-description {
  font-size: 1.5vmax;
}

/* 开始使用按钮 */
.hero-actions {
  display: flex;
  align-items: center;
  /* 全局 .el-button + .el-button 的 margin 已被置 0，这里显式给间距 */
  gap: 3vw;
  padding: 3vh 0;
}

/* 开始使用按钮 */
.hero-actions-left {
  /* hero 的主 CTA 比页面其他按钮大一档：字号 +20%，内边距同步放大 */
  --btn-padding-y: 1.4vh;
  --btn-padding-x: 2.4vw;
  font-size: 1.8vmax;
  font-weight: bold;
  background: linear-gradient(135deg,
      var(--app-color-blue-light-2),
      var(--app-color-purple));
  box-shadow: 0 4px 16px color-mix(in oklch, var(--app-color-blue) 20%, transparent);
  transition: all 0.2s ease;
}

.hero-actions-left:hover {
  background: linear-gradient(135deg,
      var(--app-color-purple-light-1),
      var(--app-color-blue-light-3));
  box-shadow: 0 6px 24px color-mix(in oklch, var(--app-color-purple) 30%, transparent);
}

.hero-actions-left:active {
  background: var(--app-color-blue);
  box-shadow: 0 2px 8px color-mix(in oklch, var(--app-color-purple) 30%, transparent);
  transform: translateY(1px);
}

/* 功能特性 */
.hero-feature-row {
  display: flex;
  align-items: center;
  justify-content: center;
}

/* 功能特性项 */
.hero-feature-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  position: relative;
  padding: 0 2vw;
}

/* 分割线 */
.hero-feature-item:not(:last-child)::after {
  content: "";
  position: absolute;
  right: 0;
  top: 20%;
  height: 60%;
  width: 1px;
  background-color: var(--app-color-black);
}

/* 功能特性数字 */
.hero-feature-num {
  font-size: 2vmax;
  font-weight: bold;
}

/* 功能特性描述 */
.hero-feature-desc {
  font-size: 1vmax;
}

.preview {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 3vh;
  padding: 5vh 12.5vw;
}

/* 标题行：与演示播放器同宽 */
.preview-head {
  width: 100%;
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 2vw;
}

.preview-head-title {
  font-size: 2.2vmax;
  font-weight: bold;
}

.preview-head-subtitle {
  font-size: 1.1vmax;
  margin-top: 0.8vh;
  color: var(--app-text-color-regular);
}

.features {
  padding: 5vh 8vw;
}

.feature-header {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 0 0 3vh 0;
}

.feature-title {
  font-size: 2.5vmax;
  font-weight: bold;
}

.feature-subtitle {
  font-size: 1.5vmax;
}

.feature-card-list {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 4vw;
}

.feature-card {
  background-color: color-mix(in oklab,
      var(--app-color-white) 60%,
      transparent);
  border-radius: 1vmax;
  box-shadow: 0 12px 40px color-mix(in oklch, var(--app-color-blue) 80%, transparent);
  display: flex;
  flex-direction: column;
  gap: 1vh;
  padding: 2vh 2vw;
}

.feature-card-header {
  display: flex;
  align-items: center;
  gap: 1vw;
  font-size: 1.5vmax;
}

.feature-card-header-icon {
  width: 3vmax;
  height: 3vmax;
  border-radius: 1vmax;
  display: flex;
  align-items: center;
  justify-content: center;
}

.icon-blue-lighter {
  background-color: color-mix(in oklch,
      var(--app-color-blue) 30%,
      var(--app-color-white-blue));
}

.icon-blue-light {
  background-color: color-mix(in oklch,
      var(--app-color-blue) 40%,
      var(--app-color-white-blue));
}

.icon-purple-light {
  background-color: color-mix(in oklch,
      var(--app-color-purple) 40%,
      var(--app-color-white-purple));
}

.icon-green-light {
  background-color: color-mix(in oklch,
      var(--app-color-green) 40%,
      var(--app-color-white-green));
}

.feature-card-header-icon svg {
  display: block;
}

.feature-card-title {
  font-weight: bold;
}

.feature-card-desc {
  font-size: 1.2vmax;
}

.workflow {
  padding: 5vh 8vw;
}

.workflow-header {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 0 0 3vh 0;
}

.workflow-header-title {
  font-size: 2.5vmax;
  font-weight: bold;
}

.workflow-header-subtitle {
  font-size: 1.5vmax;
}

.workflow-steps {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 3vw;
}

.workflow-steps-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 1vh;
}

.workflow-steps-icon {
  width: 5vmax;
  height: 5vmax;
  border-radius: 5vmax;
  display: flex;
  align-items: center;
  justify-content: center;
}

.workflow-steps-icon svg {
  width: 60%;
  height: 60%;
  display: block;
}

.workflow-steps-item-title {
  font-size: 1.5vmax;
  font-weight: bold;
}

.workflow-steps-item-desc {
  font-size: 1.2vmax;
}

.steps-arrow {
  font-size: 2vmax;
}

/* 底部导航栏 */
.landing-footer {
  background-color: var(--app-color-blue-light-3);
}

/* 底部导航栏容器：页脚本身就是「关于」的落点，留足高度才像一块内容区，
   否则点关于滚到底只看到薄薄一条 */
.landing-footer-container {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 7vh 5vw 5vh;
  gap: 3vh;
  color: var(--el-text-color-regular);
}

/* 品牌信息 */
.landing-footer-brand {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 0.5vh;
}

.landing-footer-brand-title {
  font-size: 2vmax;
  font-weight: bold;
}

.landing-footer-brand-subtitle {
  font-size: 1.5vmax;
}

/* 导航链接 */
.landing-footer-nav {
  display: flex;
  gap: 2vw;
}

.landing-footer-nav-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 1.4vh;
}

.landing-footer-nav-item-title {
  font-size: 1.5vmax;
  font-weight: bold;
  color: var(--el-text-color-primary);
}

.landing-footer-nav-item a {
  font-size: 1.5vmax;
  color: var(--el-text-color-secondary);
}

.landing-footer-nav-item a:hover {
  color: var(--el-text-color-primary);
}

/* 版权信息 */
.landing-footer-copyright {
  text-align: center;
  font-size: 1.5vmax;
  color: var(--el-text-color-placeholder);
}

</style>
