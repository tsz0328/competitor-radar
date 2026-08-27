<script setup lang="ts">
import { Radar } from "@/components/Icons";
import { ref, onMounted, onUnmounted } from "vue";
import {
  Star,
  CaretRight,
  Bell,
  User,
  House,
  Collection,
  Warning,
  Document,
  TrendCharts,
  Setting,
  Calendar,
  ArrowRight,
} from "@element-plus/icons-vue";

const activeId = ref("home");
const navItems = ["home", "preview", "features", "workflow"];
let observer: IntersectionObserver;

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
});
onUnmounted(() => observer?.disconnect());
</script>

<template>
  <!-- 导航栏 -->
  <header class="landing-header">
    <div class="landing-header-container">
      <!-- logo -->
      <div class="landing-header-logo">
        <Radar size="1.5em" color="var(--app-color-blue)" />
        <span class="landing-header-logo-text">AI 竞品雷达</span>
      </div>

      <!-- 导航链接 -->
      <nav class="landing-header-nav">
        <a href="#home" :class="{ active: activeId === 'home' }">首页</a>
        <a href="#preview" :class="{ active: activeId === 'preview' }">产品预览</a>
        <a href="#features" :class="{ active: activeId === 'features' }">核心功能</a>
        <a href="#workflow" :class="{ active: activeId === 'workflow' }">工作流程</a>
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
          <span>用AI重新定义市场情报分析</span>
        </div>
        <!-- 标题 -->
        <div class="hero-title">
          <span class="hero-highlight">AI</span> 竞品情报雷达
        </div>
        <!-- 副标题 -->
        <div class="hero-subtitle">让市场变化，尽在掌握</div>
        <!-- 产品描述 -->
        <div class="hero-description">
          自动监控竞品动态，AI智能分析市场变化，为你提供有价值的市场情报与趋势洞察
        </div>
        <!-- 按钮 -->
        <div class="hero-actions">
          <el-button class="hero-actions-left" type="primary" @click="$router.push({ name: 'Login' })">开始使用</el-button>
          <el-button class="hero-actions-right">
            <div class="hero-actions-right-row">
              <el-icon class="hero-actions-right-icon">
                <CaretRight />
              </el-icon>
            </div>
            查看产品演示
          </el-button>
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

    <!-- 产品预览 -->
    <section class="preview" id="preview">
      <!-- 工作台 -->
      <div class="preview-dashboard">
        <!-- 头部 -->
        <header class="preview-header">
          <div class="preview-header-logo">
            <Radar size="1.5em" color="var(--app-color-blue)" /><span class="preview-header-logo-text">AI 竞品雷达</span>
          </div>
          <div class="preview-header-right">
            <el-icon>
              <Bell />
            </el-icon>
            <el-icon class="preview-header-right-avatar">
              <User />
            </el-icon>
          </div>
        </header>
        <!-- 主体 -->
        <main class="preview-main">
          <!-- 侧边栏 -->
          <aside class="preview-main-sidebar">
            <div class="preview-main-sidebar-item">
              <el-icon>
                <House />
              </el-icon>
              <span>工作台</span>
            </div>
            <div class="preview-main-sidebar-item">
              <el-icon>
                <Collection />
              </el-icon>
              <span>竞品管理</span>
            </div>
            <div class="preview-main-sidebar-item">
              <el-icon>
                <Warning />
              </el-icon>
              <span>情报事件</span>
            </div>
            <div class="preview-main-sidebar-item">
              <el-icon>
                <Document />
              </el-icon>
              <span>AI 报告</span>
            </div>
            <div class="preview-main-sidebar-item">
              <el-icon>
                <TrendCharts />
              </el-icon>
              <span>趋势分析</span>
            </div>
            <div class="preview-main-sidebar-item">
              <el-icon>
                <Setting />
              </el-icon>
              <span>设置</span>
            </div>
          </aside>
          <!-- 内容 -->
          <section class="preview-main-content">
            <header class="preview-main-content-header">
              <!-- 欢迎 -->
              <div>
                <div class="preview-main-content-header-welcome">
                  早上好，用户
                </div>
                <div class="preview-main-content-header-subtitle">
                  这是您今天的竞品情报概览
                </div>
              </div>
              <!-- 日期 -->
              <div class="preview-main-content-header-date">
                <el-icon>
                  <Calendar />
                </el-icon>
                <span>2026年12月25日</span>
                <el-icon>
                  <ArrowRight />
                </el-icon>
              </div>
            </header>

            <div class="preview-main-content-stats">
              <div class="preview-main-content-stats-card">
                <div class="preview-main-content-stats-card-label">
                  监控竞品
                </div>
                <div class="preview-main-content-stats-card-value">12</div>
                <div class="preview-main-content-stats-card-trend">
                  <span>+2</span>
                  本周新增
                </div>
              </div>
              <div class="preview-main-content-stats-card">
                <div class="preview-main-content-stats-card-label">
                  新增事件
                </div>
                <div class="preview-main-content-stats-card-value">28</div>
                <div class="preview-main-content-stats-card-trend">
                  <span>+12%</span>
                  较上周
                </div>
              </div>
              <div class="preview-main-content-stats-card">
                <div class="preview-main-content-stats-card-label">AI 报告</div>
                <div class="preview-main-content-stats-card-value">6</div>
                <div class="preview-main-content-stats-card-trend">
                  <span>+2</span>
                  本周新增
                </div>
              </div>
              <div class="preview-main-content-stats-card">
                <div class="preview-main-content-stats-card-label">
                  风险提醒
                </div>
                <div class="preview-main-content-stats-card-value">3</div>
                <div class="preview-main-content-stats-card-trend">
                  需要关注
                </div>
              </div>
            </div>

            <div class="preview-body">
              <div class="preview-body-chart-card">
                <div class="preview-body-chart-card-title">竞品动态趋势</div>
                <!-- 图例 -->
                <div class="chart-legend">
                  <div class="legend-item">
                    <span class="legend-line color-blue"></span>
                    <span>功能更新</span>
                  </div>
                  <div class="legend-item">
                    <span class="legend-line color-purple"></span>
                    <span>价格变动</span>
                  </div>
                  <div class="legend-item">
                    <span class="legend-line color-green"></span>
                    <span>舆论热度</span>
                  </div>
                </div>
                <!-- 图表 -->
                <div class="preview-body-chart">
                  <svg class="preview-chart-svg" viewBox="0 0 425 180" preserveAspectRatio="none"
                    xmlns="http://www.w3.org/2000/svg">
                    <defs>
                      <!-- 蓝色渐变：功能更新 -->
                      <linearGradient id="area-blue" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stop-color="var(--app-color-blue)" stop-opacity="0.25" />
                        <stop offset="100%" stop-color="var(--app-color-blue)" stop-opacity="0.02" />
                      </linearGradient>
                      <!-- 紫色渐变：价格变动 -->
                      <linearGradient id="area-purple" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stop-color="var(--app-color-purple)" stop-opacity="0.2" />
                        <stop offset="100%" stop-color="var(--app-color-purple)" stop-opacity="0.02" />
                      </linearGradient>
                      <!-- 绿色渐变：舆论热度 -->
                      <linearGradient id="area-green" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stop-color="var(--app-color-green)" stop-opacity="0.2" />
                        <stop offset="100%" stop-color="var(--app-color-green)" stop-opacity="0.02" />
                      </linearGradient>
                    </defs>

                    <!-- 水平网格虚线 -->
                    <g stroke="#e5e7eb" stroke-width="1" stroke-dasharray="3 3">
                      <line x1="30" y1="10" x2="410" y2="10" />
                      <line x1="30" y1="46.25" x2="410" y2="46.25" />
                      <line x1="30" y1="82.5" x2="410" y2="82.5" />
                      <line x1="30" y1="118.75" x2="410" y2="118.75" />
                      <line x1="30" y1="155" x2="410" y2="155" />
                    </g>

                    <!-- 纵轴刻度 0-20 -->
                    <g fill="#909399" font-size="12" text-anchor="end" font-family="system-ui">
                      <text x="25" y="14">20</text>
                      <text x="25" y="50.25">15</text>
                      <text x="25" y="86.5">10</text>
                      <text x="25" y="122.75">5</text>
                      <text x="25" y="159">0</text>
                    </g>

                    <!-- 横轴日期刻度 -->
                    <g fill="#909399" font-size="12" text-anchor="middle" font-family="system-ui">
                      <text x="30" y="172">6/19</text>
                      <text x="93.33" y="172">6/20</text>
                      <text x="156.67" y="172">6/21</text>
                      <text x="220" y="172">6/22</text>
                      <text x="283.33" y="172">6/23</text>
                      <text x="346.67" y="172">6/24</text>
                      <text x="410" y="172">6/25</text>
                    </g>

                    <!-- 舆论热度（最底层绿色面积） -->
                    <path
                      d="M30,155 C62,137 94,126 125,118.8 S188,126 220,93.4 S283,105 315,118.8 S378,100 410,81 L410,155 L30,155 Z"
                      fill="url(#area-green)" />

                    <!-- 价格变动（中间层紫色面积） -->
                    <path
                      d="M30,112 C62,98 94,88 125,82 S188,92 220,66 S283,76 315,85 S378,55 410,28 L410,155 L30,155 Z"
                      fill="url(#area-purple)" />

                    <!-- 功能更新（最上层蓝色面积） -->
                    <path
                      d="M30,97 C62,81 94,69 125,64.4 S188,75 220,46.3 S283,58 315,68 S378,42 410,10 L410,155 L30,155 Z"
                      fill="url(#area-blue)" />

                    <!-- 功能更新：蓝色主折线 -->
                    <path d="M30,97 C62,81 94,69 125,64.4 S188,75 220,46.3 S283,58 315,68 S378,42 410,10" fill="none"
                      stroke="var(--app-color-blue)" stroke-width="2.5" stroke-linecap="round"
                      stroke-linejoin="round" />

                    <!-- 价格变动：紫色折线 -->
                    <path d="M30,112 C62,98 94,88 125,82 S188,92 220,66 S283,76 315,85 S378,55 410,28" fill="none"
                      stroke="var(--app-color-purple)" stroke-width="2" stroke-linecap="round"
                      stroke-linejoin="round" />

                    <!-- 舆论热度：绿色折线 -->
                    <path d="M30,155 C62,137 94,126 125,118.8 S188,126 220,93.4 S283,105 315,118.8 S378,100 410,81"
                      fill="none" stroke="var(--app-color-green)" stroke-width="2" stroke-linecap="round"
                      stroke-linejoin="round" />
                  </svg>
                </div>
              </div>

              <div class="preview-new-card">
                <div class="preview-new-card-title">最新 AI 洞察</div>
                <div class="preview-new-card-list">
                  <div class="preview-new-card-list-item">
                    <div class="preview-new-card-list-item-title">
                      Claude 发布新模型能力
                    </div>
                    <div class="preview-new-card-list-item-desc">
                      在长文本理解方面取得显著提升
                    </div>
                    <div class="preview-new-card-list-item-date">2小时前</div>
                  </div>
                  <div class="preview-new-card-list-item">
                    <div class="preview-new-card-list-item-title">
                      OpenAI 调整 API 定价策略
                    </div>
                    <div class="preview-new-card-list-item-desc">
                      部分模型价格下调 20%
                    </div>
                    <div class="preview-new-card-list-item-date">5小时前</div>
                  </div>
                  <div class="preview-new-card-list-item">
                    <div class="preview-new-card-list-item-title">
                      Midjourney 上线视频生成功能
                    </div>
                    <div class="preview-new-card-list-item-desc">
                      正式进军 AI 视频领域
                    </div>
                    <div class="preview-new-card-list-item-date">1天前</div>
                  </div>
                </div>
              </div>
            </div>
          </section>
        </main>
      </div>
    </section>

    <!-- 功能特性 -->
    <section class="features" id="features">
      <!-- 功能特性标题 -->
      <div class="feature-header">
        <div class="feature-title">核心功能</div>
        <div class="feature-subtitle">
          AI 驱动的全流程竞品情报分析，助你抢占市场先机
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
            基于 Playwright
            智能抓取技术，7×24小时持续监控竞品官网、更新日志、社交媒体等多渠道信息，第一时间发现变化。
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
            通过大语言模型深度分析竞品动态，自动提取关键信息，判断变化类型，生成专业的情报摘要与市场洞察。
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

  <!-- 底部导航栏 -->
  <footer class="landing-footer">
    <!-- 底部导航栏容器 -->
    <div class="landing-footer-container">
      <!-- 品牌信息 -->
      <div class="landing-footer-brand">
        <span class="landing-footer-brand-title">AI 竞品雷达</span>
        <span class="landing-footer-brand-subtitle">让AI成为你的市场情报助手</span>
      </div>

      <!-- 导航链接 -->
      <nav class="landing-footer-nav">
        <!-- 产品 -->
        <div class="landing-footer-nav-item">
          <span class="landing-footer-nav-item-title">产品</span>
          <a href="#features">功能介绍</a>
          <a href="#workflow">工作流程</a>
          <a href="#preview">产品预览</a>
        </div>

        <!-- 关于 -->
        <div class="landing-footer-nav-item">
          <span class="landing-footer-nav-item-title">关于</span>
          <a href="#">团队博客</a>
          <a href="#">联系我们</a>
        </div>

        <!-- 法律 -->
        <div class="landing-footer-nav-item">
          <span class="landing-footer-nav-item-title">法律</span>
          <a href="#">隐私政策</a>
          <a href="#">服务条款</a>
          <a href="https://github.com/tsz0328/ai-competitor-radar.git" target="_blank">GitHub</a>
        </div>
      </nav>

      <!-- 版权信息 -->
      <div class="landing-footer-copyright">
        <span>© 2026 AI Competitor Radar. All rights reserved.</span>
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

/* logo */
.landing-header-logo {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 1vw;
  font-weight: bold;
  cursor: pointer;
  font-size: 2vmax;
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
  padding: 3vh 0;
}

/* 开始使用按钮 */
.hero-actions-left {
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

/* 查看产品演示按钮 */
.hero-actions-right {
  position: relative;
  padding: var(--btn-padding-y) var(--btn-padding-x) var(--btn-padding-y) calc(2 * var(--btn-padding-x));
  background-color: transparent;
  transition: all 0.2s ease;
}

.hero-actions-right:hover {
  background-color: color-mix(in oklch,
      var(--app-color-blue-light-5) 10%,
      transparent);
  border-color: var(--app-color-white);
}

.hero-actions-right:active {
  background-color: color-mix(in oklch,
      var(--app-color-purple) 12%,
      transparent);
}

/* 查看产品演示按钮行 */
.hero-actions-right-row {
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: calc(2 * var(--btn-padding-x));
  display: flex;
  align-items: center;
  justify-content: center;
}

/* 查看产品演示按钮图标 */
.hero-actions-right-icon {
  font-size: 2vmax;
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
  align-items: center;
  justify-content: center;
  padding: 5vh 0;
}

.preview-dashboard {
  border-radius: 2vmax;
  overflow: hidden;
  box-shadow: 0 12px 40px color-mix(in oklch, var(--app-color-blue) 80%, transparent);
  width: 75vw;
}

.preview-header {
  padding: 1vh 2vw;
  display: flex;
  justify-content: space-between;
  background-color: color-mix(in oklab,
      var(--app-color-white) 60%,
      transparent);
}

.preview-header-logo {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 1vw;
  font-weight: bold;
  font-size: 1.5vmax;
}

.preview-header-right {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 2vw;
  font-size: 2vmax;
}

.preview-header-right-avatar {
  background-color: var(--app-color-blue-light-3);
  width: 2.2vmax;
  height: 2.2vmax;
  border-radius: 100%;
}

.preview-main {
  background-color: color-mix(in oklab,
      var(--app-color-white) 30%,
      transparent);
  display: flex;
}

.preview-main-sidebar {
  font-size: 1.5vmax;
  padding: 2vh 1vw;
  border-right: 1px solid color-mix(in oklch, var(--app-color-black) 10%, transparent);
}

.preview-main-sidebar-item {
  padding: 1vh 2vw 1vh 1vw;
  display: flex;
  align-items: center;
  gap: 1vw;
  border-radius: 1vmax;
}

.preview-main-sidebar-item:first-child {
  background-color: color-mix(in oklab, var(--app-color-blue) 30%, transparent);
}

.preview-main-content {
  display: flex;
  flex-direction: column;
  gap: 2vh;
  justify-content: center;
  padding: 2vh 2vw;
  flex: 1;
}

.preview-main-content-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.preview-main-content-header-welcome {
  font-size: 2vmax;
  font-weight: bold;
}

.preview-main-content-header-subtitle {
  font-size: 1vmax;
}

.preview-main-content-header-date {
  border-radius: 1vmax;
  padding: 1vh 1vw;
  display: flex;
  align-items: center;
  gap: 0.5vw;
  font-size: 1vmax;
}

.preview-main-content-stats {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.preview-main-content-stats-card {
  background-color: color-mix(in oklab,
      var(--app-color-white) 60%,
      transparent);
  border-radius: 1vmax;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.12);
  padding: 1vh 3vw 1vh 1vw;
}

.preview-main-content-stats-card-label {
  font-size: 1.2vmax;
  font-weight: bold;
}

.preview-main-content-stats-card-value {
  font-size: 1.5vmax;
  font-weight: bold;
}

.preview-main-content-stats-card-trend {
  font-size: 1vmax;
}

.preview-body {
  display: flex;
  gap: 2vw;
}

.preview-body-chart-card {
  background-color: color-mix(in oklab,
      var(--app-color-white) 60%,
      transparent);
  padding: 1vh 1vw;
  border-radius: 1vmax;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.12);
  display: flex;
  flex-direction: column;
  gap: 1vh;
  flex: 2;
  min-width: 0;
}

.preview-body-chart-card-title {
  font-size: 1.1vmax;
  font-weight: bold;
}

.chart-legend {
  display: flex;
  justify-content: flex-end;
  gap: 1vw;
}

.legend-item {
  display: flex;
  align-items: center;
  font-size: 1vmax;
  gap: 0.5vw;
}

.legend-line {
  width: 2vw;
  height: 0.8vh;
  border-radius: 0.8vh;
}

.color-blue {
  background-color: var(--app-color-blue);
}

.color-purple {
  background-color: var(--app-color-purple);
}

.color-green {
  background-color: var(--app-color-green);
}

.preview-body-chart {
  width: 100%;
}

.preview-chart-svg {
  width: 100%;
  height: 100%;
  display: block;
}

.preview-new-card {
  background-color: color-mix(in oklab,
      var(--app-color-white) 60%,
      transparent);
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.12);
  border-radius: 1vmax;
  padding: 1vh 1vw;
  flex: 1;
  min-width: 0;
}

.preview-new-card-title {
  font-size: 1.3vmax;
  font-weight: bold;
  padding: 1vh 1vw 1vh 0;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}

.preview-new-card-list {
  display: flex;
  flex-direction: column;
  gap: 1vh;
}

.preview-new-card-list-item-title {
  font-size: 1.2vmax;
  font-weight: bold;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}

.preview-new-card-list-item-desc {
  font-size: 1vmax;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}

.preview-new-card-list-item-date {
  font-size: 1vmax;
  color: var(--app-color-gray);
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

/* 底部导航栏容器 */
.landing-footer-container {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 4vh 5vw 2vh;
  gap: 1vh;
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
  gap: 1vh;
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
