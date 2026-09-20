<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import { useReportStore } from "@/stores/report";
import { marked } from "marked";
import DOMPurify from "dompurify";
import type { ReportListItem } from "@/types/report";
import { generateReport } from "@/api/report";
import DonutChart from "@/components/Charts/DonutChart.vue";
import RankBarChart from "@/components/Charts/RankBarChart.vue";
import CompareLineChart from "@/components/Charts/CompareLineChart.vue";
import {
  Search,
  Star,
  StarFilled,
  Download,
  Share,
  MoreFilled,
  Document,
  Monitor,
  Promotion,
  PriceTag,
  Warning,
  Filter,
  Plus,
} from "@element-plus/icons-vue";

const reportStore = useReportStore();
const router = useRouter();

/** 周报相关事件 → 情报中心（带 id 直接打开该事件详情） */
function goToEvent(id: number) {
  router.push({ name: "Event", query: { id: String(id) } });
}
/** 周报涉及竞品 → 竞品管理（按名称预填，定位到该竞品） */
function goToCompetitor(name: string) {
  router.push({ name: "Competitor", query: { keyword: name } });
}

// 左侧列表状态
const keyword = ref("");
const typeFilter = ref<"all" | "weekly" | "monthly">("all");
const onlyFavorite = ref(false);

// 右侧详情状态
const activeId = ref<number | null>(null);
const activeTab = ref<"content" | "full" | "events" | "competitors" | "ai">("content");

onMounted(async () => {
  await reportStore.loadReportList();
  const first = reportStore.reportList?.reports[0];
  if (first) selectReport(first.id);
});

function selectReport(id: number) {
  activeId.value = id;
  activeTab.value = "content";
  reportStore.loadReportDetail(id);
}

// 列表过滤 + 按月分组
const reports = computed(() => reportStore.reportList?.reports ?? []);
const filteredReports = computed(() =>
  reports.value.filter((r) => {
    if (typeFilter.value !== "all" && r.type !== typeFilter.value) return false;
    if (onlyFavorite.value && !r.favorite) return false;
    if (keyword.value && !r.title.includes(keyword.value.trim())) return false;
    return true;
  }),
);
const groupedReports = computed(() => {
  const map = new Map<string, ReportListItem[]>();
  for (const r of filteredReports.value) {
    if (!map.has(r.monthGroup)) map.set(r.monthGroup, []);
    map.get(r.monthGroup)!.push(r);
  }
  return [...map.entries()].map(([month, items]) => ({ month, items }));
});

const detail = computed(() => reportStore.reportDetail);

// 后端 content 是 AI 生成的 Markdown，渲染进 v-html 前先用 DOMPurify 清一遍，避免注入脚本
const renderedContent = computed(() => {
  const raw = detail.value?.content?.trim();
  if (!raw) return "";
  return DOMPurify.sanitize(marked.parse(raw, { gfm: true, breaks: true }) as string);
});

// 核心摘要统计卡片：展示配置（稳定，留前端）+ 数值来自接口
const STAT_DEFS = [
  { key: "events", icon: Document, cls: "stat-purple" },
  { key: "competitors", icon: Monitor, cls: "stat-blue" },
  { key: "feature", icon: Promotion, cls: "stat-green" },
  { key: "price", icon: PriceTag, cls: "stat-orange" },
  { key: "impact", icon: Warning, cls: "stat-red" },
] as const;

const statCards = computed(() => {
  const stats = detail.value?.stats ?? [];
  return STAT_DEFS.map((d) => {
    const s = stats.find((item) => item.key === d.key);
    return {
      ...d,
      label: s?.label ?? "",
      value: s?.value ?? 0,
      delta: s?.delta ?? 0,
      deltaType: s?.deltaType ?? "up",
    };
  });
});

// 竞争动态：本期各竞品的变化条数，用排行榜最大值做条形比例
const maxCompetitorChanges = computed(() =>
  Math.max(1, ...(detail.value?.relatedCompetitors ?? []).map((c) => c.changes)),
);
function motionWidth(changes: number): string {
  return `${Math.round((changes / maxCompetitorChanges.value) * 100)}%`;
}

// 手动生成本周周报（定时生成留待里程碑 10）
const generating = ref(false);

async function onGenerate() {
  if (generating.value) return;
  generating.value = true;
  try {
    const created = await generateReport();
    ElMessage.success("周报已生成");
    await reportStore.loadReportList();
    activeId.value = created.id;
    activeTab.value = "content";
    reportStore.loadReportDetail(created.id);
  } catch {
    // 失败提示由 request.ts 拦截器统一弹出
  } finally {
    generating.value = false;
  }
}

async function onToggleFavorite(id: number) {
  try {
    const next = await reportStore.toggleFavorite(id);
    ElMessage.success(next ? "已收藏该报告" : "已取消收藏");
  } catch {
    // 失败提示由 request.ts 拦截器统一弹出
  }
}

function onDownload() {
  if (!activeId.value) return;
  window.open(`/api/reports/${activeId.value}/export`, "_blank", "noopener");
}

async function onShare() {
  try {
    await navigator.clipboard.writeText(window.location.href);
    ElMessage.success("分享链接已复制到剪贴板");
  } catch {
    ElMessage.warning("复制失败，请手动复制当前链接");
  }
}
</script>

<template>
  <div class="report-page">
    <!-- 左侧：报告列表 -->
    <aside class="report-side card">
        <el-input
          v-model="keyword"
          class="side-search"
          placeholder="搜索报告标题或关键词..."
          :prefix-icon="Search"
          clearable
        />
        <div class="side-filter-row">
          <el-popover placement="bottom-start" trigger="click" width="220">
            <template #reference>
              <el-button :icon="Filter">筛选</el-button>
            </template>
            <div class="filter-pop">
              <div class="filter-pop-label">报告类型</div>
              <el-radio-group v-model="typeFilter" class="filter-pop-radios">
                <el-radio value="all">全部</el-radio>
                <el-radio value="weekly">周报</el-radio>
                <el-radio value="monthly">月报</el-radio>
              </el-radio-group>
              <el-checkbox v-model="onlyFavorite">仅看收藏</el-checkbox>
            </div>
          </el-popover>
          <el-button
            type="primary"
            :icon="Plus"
            :loading="generating"
            @click="onGenerate"
          >
            生成
          </el-button>
        </div>

        <div class="report-list" v-loading="reportStore.listLoading">
          <div v-for="g in groupedReports" :key="g.month" class="report-group">
            <div class="month-label">{{ g.month }}</div>
            <div
              v-for="r in g.items"
              :key="r.id"
              class="report-item"
              :class="{ 'is-active': r.id === activeId }"
              @click="selectReport(r.id)"
            >
              <div class="report-item-icon">
                <el-icon><Document /></el-icon>
              </div>
              <div class="report-item-text">
                <div class="report-item-title">{{ r.title }}</div>
                <div class="report-item-meta">
                  {{ r.range }} · {{ r.competitors }} 个竞品
                </div>
                <div class="report-item-date">{{ r.generatedAt }} 生成</div>
              </div>
              <el-icon
                class="report-item-star"
                :class="{ 'is-fav': r.favorite }"
                @click.stop="onToggleFavorite(r.id)"
              >
                <StarFilled v-if="r.favorite" />
                <Star v-else />
              </el-icon>
            </div>
          </div>
          <el-empty
            v-if="!reportStore.listLoading && !filteredReports.length"
            description="没有符合条件的报告"
            :image-size="80"
          />
        </div>

        <footer class="side-footer">
          共 {{ reportStore.reportList?.total ?? 0 }} 份报告
        </footer>
    </aside>

    <!-- 右侧：报告详情 -->
    <main class="report-main" v-loading="reportStore.detailLoading">
      <template v-if="detail">
        <header class="report-header card">
          <div class="header-left">
            <div class="header-title-row">
              <span class="header-title">{{ detail.title }}</span>
              <span class="header-tag">{{ detail.typeLabel }}</span>
            </div>
            <div class="header-meta">
              {{ detail.rangeStart }} ~ {{ detail.rangeEnd }}（共监控
              {{ detail.competitors }} 个竞品）
            </div>
          </div>
          <div class="header-actions">
            <el-button
              :icon="detail.favorite ? StarFilled : Star"
              :class="{ 'is-fav': detail.favorite }"
              @click="onToggleFavorite(detail.id)"
            >
              收藏
            </el-button>
            <el-button :icon="Download" @click="onDownload">
              导出 PDF
            </el-button>
            <el-button :icon="Share" @click="onShare">分享</el-button>
            <el-button :icon="MoreFilled" text />
          </div>
        </header>

        <div class="report-body card">
          <el-tabs v-model="activeTab" class="report-tabs">
            <el-tab-pane label="报告内容" name="content" />
            <el-tab-pane label="正文" name="full" />
            <el-tab-pane
              :label="`相关事件 (${detail.relatedEvents.length})`"
              name="events"
            />
            <el-tab-pane
              :label="`涉及竞品 (${detail.relatedCompetitors.length})`"
              name="competitors"
            />
            <el-tab-pane label="AI 分析过程" name="ai" />
          </el-tabs>

          <div class="tab-content">
            <!-- 报告内容 -->
            <div v-show="activeTab === 'content'" class="content-tab">
              <section class="section">
                <h3 class="section-title">一、本周核心摘要</h3>
                <p class="summary-text">{{ detail.summary }}</p>
                <div class="stat-grid">
                  <div v-for="s in statCards" :key="s.key" class="stat-item">
                    <div class="stat-item-head">
                      <el-icon class="stat-icon" :class="s.cls">
                        <component :is="s.icon" />
                      </el-icon>
                      <span class="stat-label">{{ s.label }}</span>
                    </div>
                    <div class="stat-value">{{ s.value }}</div>
                    <div class="stat-delta" :class="s.deltaType">
                      较上周 {{ s.deltaType === "up" ? "↑" : "↓" }}
                      {{ s.delta }}%
                    </div>
                  </div>
                </div>
              </section>

              <section class="section">
                <h3 class="section-title">二、本周重点变化</h3>
                <div
                  v-for="(h, i) in detail.highlights"
                  :key="h.id"
                  class="highlight"
                >
                  <div class="highlight-head">
                    <span class="highlight-title">
                      {{ i + 1 }}. {{ h.title }}
                    </span>
                    <span class="highlight-tag" :class="h.tagType">
                      {{ h.tag }}
                    </span>
                    <span class="highlight-impact" :class="h.impactType">
                      {{ h.impact }}
                    </span>
                  </div>
                  <ul class="highlight-points">
                    <li v-for="(p, pi) in h.points" :key="pi">{{ p }}</li>
                  </ul>
                  <div class="highlight-foot">
                    <span>影响竞品：{{ h.affected.join("、") }}</span>
                    <span>发现时间：{{ h.foundAt }}</span>
                    <span>AI 置信度：{{ h.aiConfidence }}%</span>
                  </div>
                </div>
              </section>

              <section class="section">
                <h3 class="section-title">三、竞争动态</h3>
                <div v-if="detail.relatedCompetitors.length" class="motion-list">
                  <div
                    v-for="c in detail.relatedCompetitors"
                    :key="c.name"
                    class="motion-item"
                  >
                    <div
                      class="motion-icon"
                      :style="{ backgroundColor: c.iconBg, color: c.iconColor }"
                    >
                      {{ c.iconText }}
                    </div>
                    <div class="motion-name">{{ c.name }}</div>
                    <div class="motion-bar">
                      <i :style="{ width: motionWidth(c.changes) }" />
                    </div>
                    <div class="motion-changes">{{ c.changes }} 条</div>
                  </div>
                </div>
                <p v-else class="motion-empty">本期没有检测到竞品变化。</p>
              </section>

              <section class="section">
                <h3 class="section-title">四、按类别统计</h3>
                <div class="chart-grid">
                  <div class="chart-card">
                    <div class="chart-title">事件类型分布</div>
                    <donut-chart :data="detail.categoryDist" height="220px" />
                  </div>
                  <div class="chart-card">
                    <div class="chart-title">竞品活跃度 TOP5</div>
                    <rank-bar-chart
                      :data="detail.competitorRank"
                      height="220px"
                    />
                  </div>
                  <div class="chart-card">
                    <div class="chart-title">高影响事件趋势</div>
                    <compare-line-chart
                      :trend="detail.impactTrend"
                      height="220px"
                    />
                  </div>
                </div>
              </section>
            </div>

            <!-- AI 周报正文（Markdown） -->
            <div v-show="activeTab === 'full'" class="full-tab">
              <article
                v-if="renderedContent"
                class="markdown-body"
                v-html="renderedContent"
              ></article>
              <el-empty v-else description="本期报告暂无 AI 正文" :image-size="80" />
            </div>

            <!-- 相关事件 -->
            <div v-show="activeTab === 'events'" class="events-tab">
              <div
                v-for="e in detail.relatedEvents"
                :key="e.id"
                class="related-event"
                @click="goToEvent(e.id)"
              >
                <span class="event-tag" :class="e.tagType">{{ e.tag }}</span>
                <div class="related-event-body">
                  <div class="related-event-title">{{ e.title }}</div>
                  <div class="related-event-meta">
                    {{ e.brand }} · {{ e.time }}
                  </div>
                </div>
              </div>
            </div>

            <!-- 涉及竞品 -->
            <div v-show="activeTab === 'competitors'" class="competitors-tab">
              <div
                v-for="c in detail.relatedCompetitors"
                :key="c.name"
                class="competitor-card"
                @click="goToCompetitor(c.name)"
              >
                <div
                  class="competitor-logo"
                  :style="{ backgroundColor: c.iconBg, color: c.iconColor }"
                >
                  {{ c.iconText }}
                </div>
                <div class="competitor-name">{{ c.name }}</div>
                <div class="competitor-changes">{{ c.changes }} 条变化</div>
              </div>
            </div>

            <!-- AI 分析过程 -->
            <div v-show="activeTab === 'ai'" class="ai-tab">
              <el-timeline>
                <el-timeline-item
                  v-for="(s, i) in detail.aiSteps"
                  :key="i"
                  :timestamp="s.time"
                  placement="top"
                  :type="i === detail.aiSteps.length - 1 ? 'primary' : ''"
                >
                  <div class="ai-step-title">{{ s.title }}</div>
                  <div class="ai-step-desc">{{ s.desc }}</div>
                </el-timeline-item>
              </el-timeline>
            </div>
          </div>
        </div>
      </template>

      <el-empty
        v-else-if="!reportStore.detailLoading"
        class="main-empty"
        description="请选择左侧报告查看详情"
      />
    </main>
  </div>
</template>

<style scoped>
.report-page {
  height: 100%;
  padding: 2vh 2vw;
  display: grid;
  grid-template-columns: minmax(260px, 1fr) 3.2fr;
  gap: 1.5vw;
  overflow: hidden;
}

.card {
  background-color: var(--app-color-white);
  border-radius: 1vmax;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.1);
}

/* ===== 左侧列表 ===== */
.report-side {
  display: flex;
  flex-direction: column;
  padding: 1.5vh 1vw;
  gap: 1.2vh;
  min-height: 0;
}

.side-search {
  font-size: 1vmax;
}

.side-filter-row {
  display: flex;
  gap: 0.8vw;
}

.side-select {
  flex: 1;
  min-width: 0;
}

.side-filter-row .el-button {
  margin-left: 0;
  font-size: 1vmax;
}

.filter-pop {
  display: flex;
  flex-direction: column;
  gap: 1vh;
}

.filter-pop-label {
  font-size: 1vmax;
  font-weight: bold;
}

.filter-pop-radios {
  display: flex;
  gap: 1vw;
}

.report-list {
  padding: 0 0.1vw;
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
}

.report-group {
  display: flex;
  flex-direction: column;
  gap: 1vh;
}

.month-label {
  font-size: 1vmax;
  color: var(--app-color-gray);
  padding: 0.8vh 0 0.4vh;
}

.report-item {
  display: flex;
  align-items: flex-start;
  gap: 0.8vw;
  padding: 1vh 0.6vw;
  border-radius: 0.8vmax;
  cursor: pointer;
}

.report-item:hover {
  background-color: var(--app-color-blue-light-5);
}

.report-item.is-active {
  background-color: var(--app-color-blue-light-5);
  outline: 1px solid var(--app-color-blue-light-3);
}

.report-item-icon {
  width: 3vmax;
  height: 3vmax;
  min-width: 28px;
  min-height: 28px;
  border-radius: 0.6vmax;
  background-color: var(--app-color-purple-light-4);
  color: var(--app-color-purple);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1.4vmax;
  flex-shrink: 0;
}

.report-item-text {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 0.2vh;
}

.report-item-title {
  font-size: 1.1vmax;
  font-weight: bold;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.report-item-meta,
.report-item-date {
  font-size: 0.9vmax;
  color: var(--app-color-gray);
}

.report-item-star {
  font-size: 1.2vmax;
  flex-shrink: 0;
}

.report-item-star.is-fav {
  color: #f7ba2a;
}

.side-footer {
  font-size: 0.9vmax;
  color: var(--app-color-gray);
  border-top: 1px solid var(--app-color-blue-light-4);
  padding-top: 1vh;
}

/* ===== 右侧详情 ===== */
.report-main {
  display: flex;
  flex-direction: column;
  gap: 1.5vh;
  min-height: 0;
}

.report-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1.5vh 1.5vw;
  flex-shrink: 0;
}

.header-title-row {
  display: flex;
  align-items: center;
  gap: 0.8vw;
}

.header-title {
  font-size: 1.4vmax;
  font-weight: bold;
}

.header-tag {
  font-size: 0.9vmax;
  padding: 0 0.5vw;
  border-radius: 0.4vmax;
  background-color: var(--app-color-purple-light-4);
  color: var(--app-color-purple);
}

.header-meta {
  font-size: 0.9vmax;
  color: var(--app-color-gray);
  margin-top: 0.4vh;
}

.header-actions {
  display: flex;
  align-items: center;
}

.header-actions .el-button {
  font-size: 1vmax;
  margin-left: 0.8vw;
}

/* 收藏后按钮与图标统一高亮，和左侧列表的星标保持一致 */
.header-actions .el-button.is-fav {
  color: #f7ba2a;
  border-color: #f7ba2a;
}
.header-actions .el-button.is-fav :deep(svg) {
  color: #f7ba2a;
}

.report-body {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  padding: 0 1.5vw;
}

.report-tabs {
  flex-shrink: 0;
}

.report-tabs :deep(.el-tabs__item) {
  font-size: 1vmax;
}

.report-tabs :deep(.el-tabs__header) {
  margin-bottom: 0;
}

.tab-content {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 1.5vh 0.5vw 2vh;
}

/* ===== 报告内容 ===== */
.content-tab {
  display: flex;
  flex-direction: column;
  gap: 2.5vh;
}

.section-title {
  font-size: 1.2vmax;
  font-weight: bold;
  margin: 0 0 1vh;
}

.summary-text {
  font-size: 1vmax;
  line-height: 1.8;
  margin: 0;
  color: var(--app-text-color-regular);
}

.stat-grid {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 1vw;
  margin-top: 1.5vh;
}

.stat-item {
  border: 1px solid var(--app-color-blue-light-4);
  border-radius: 0.8vmax;
  padding: 1.2vh 1vw;
  display: flex;
  flex-direction: column;
  gap: 0.4vh;
}

.stat-item-head {
  display: flex;
  align-items: center;
  gap: 0.5vw;
}

.stat-icon {
  width: 2.2vmax;
  height: 2.2vmax;
  min-width: 24px;
  min-height: 24px;
  border-radius: 0.5vmax;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1.2vmax;
}

.stat-purple {
  background: #eceaff;
  color: #5b6fff;
}
.stat-blue {
  background: #e6f4ff;
  color: #1890ff;
}
.stat-green {
  background: #e6f9f0;
  color: #22c55e;
}
.stat-orange {
  background: #fff3e6;
  color: #fa8c16;
}
.stat-red {
  background: #fff1f0;
  color: #ff4d4f;
}

.stat-label {
  font-size: 0.9vmax;
  color: var(--app-color-gray);
}

.stat-value {
  font-size: 1.6vmax;
  font-weight: bold;
}

.stat-delta {
  font-size: 0.9vmax;
}

.stat-delta.up {
  color: #22c55e;
}

.stat-delta.down {
  color: #ff4d4f;
}

/* 重点变化 */
.highlight {
  border: 1px solid var(--app-color-blue-light-4);
  border-radius: 0.8vmax;
  padding: 1.5vh 1.2vw;
  margin-bottom: 1.5vh;
}

.highlight:last-child {
  margin-bottom: 0;
}

.highlight-head {
  display: flex;
  align-items: center;
  gap: 0.8vw;
}

.highlight-title {
  font-size: 1.1vmax;
  font-weight: bold;
}

.highlight-tag {
  font-size: 0.9vmax;
  padding: 0 0.5vw;
  border-radius: 0.4vmax;
}

.tag-feature {
  background: #e6f9f0;
  color: #22c55e;
}
.tag-price {
  background: #fff3e6;
  color: #fa8c16;
}
.tag-content {
  background: #e6f4ff;
  color: #1890ff;
}

.highlight-impact {
  margin-left: auto;
  font-size: 0.9vmax;
  padding: 0 0.5vw;
  border-radius: 0.4vmax;
}

.highlight-impact.high {
  background: #fff1f0;
  color: #ff4d4f;
}

.highlight-impact.mid {
  background: #fff3e6;
  color: #fa8c16;
}

.highlight-points {
  margin: 1vh 0;
  padding-left: 1.5vw;
  display: flex;
  flex-direction: column;
  gap: 0.5vh;
}

.highlight-points li {
  font-size: 1vmax;
  line-height: 1.7;
}

.highlight-foot {
  display: flex;
  gap: 2vw;
  font-size: 0.9vmax;
  color: var(--app-color-gray);
  border-top: 1px dashed var(--app-color-blue-light-4);
  padding-top: 1vh;
}

/* 竞争动态：每个竞品本期变化条数 */
.motion-list {
  display: flex;
  flex-direction: column;
  gap: 1vh;
}

.motion-item {
  display: flex;
  align-items: center;
  gap: 1vw;
  font-size: 1vmax;
}

.motion-icon {
  width: 2.2vmax;
  height: 2.2vmax;
  min-width: 26px;
  min-height: 26px;
  border-radius: 0.5vmax;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1vmax;
  font-weight: bold;
  flex-shrink: 0;
}

.motion-name {
  width: 10vw;
  min-width: 90px;
  flex-shrink: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.motion-bar {
  flex: 1;
  min-width: 0;
  height: 10px;
  border-radius: 100vmax;
  background: var(--app-color-blue-light-5);
  overflow: hidden;
}
.motion-bar i {
  display: block;
  height: 100%;
  border-radius: 100vmax;
  background: linear-gradient(
    90deg,
    var(--app-color-blue-light-2),
    var(--app-color-purple)
  );
}

.motion-changes {
  width: 4vw;
  min-width: 48px;
  text-align: right;
  flex-shrink: 0;
  color: var(--app-color-gray);
}

.motion-empty {
  margin: 0;
  font-size: 1vmax;
  color: var(--app-color-gray);
}

/* 图表 */
.chart-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 1vw;
}

.chart-card {
  border: 1px solid var(--app-color-blue-light-4);
  border-radius: 0.8vmax;
  padding: 1.2vh 1vw;
}

.chart-title {
  font-size: 1vmax;
  font-weight: bold;
  margin-bottom: 0.8vh;
}

/* AI 周报正文 */
.full-tab {
  padding: 0.5vw 0.5vw 2vh;
}

.markdown-body {
  max-width: 980px;
  font-size: 1vmax;
  line-height: 1.85;
  color: var(--app-text-color-regular);
}

.markdown-body :deep(h1),
.markdown-body :deep(h2),
.markdown-body :deep(h3) {
  margin: 2vh 0 1vh;
  line-height: 1.35;
}

.markdown-body :deep(h1) {
  font-size: 1.45vmax;
}

.markdown-body :deep(h2) {
  font-size: 1.25vmax;
  padding-bottom: 0.5vh;
  border-bottom: 1px solid var(--app-color-blue-light-4);
}

.markdown-body :deep(h3) {
  font-size: 1.1vmax;
}

.markdown-body :deep(p),
.markdown-body :deep(ul),
.markdown-body :deep(ol) {
  margin: 0.8vh 0 1.2vh;
}

.markdown-body :deep(ul),
.markdown-body :deep(ol) {
  padding-left: 1.8vw;
}

.markdown-body :deep(li) {
  margin: 0.35vh 0;
}

.markdown-body :deep(blockquote) {
  margin: 1.2vh 0;
  padding: 0.8vh 1vw;
  border-left: 3px solid var(--app-color-blue-light-3);
  background: var(--app-color-blue-light-5);
  color: var(--app-color-gray);
}

.markdown-body :deep(code) {
  padding: 0.1em 0.35em;
  border-radius: 0.35em;
  background: #f5f5f5;
  font-family: Consolas, Menlo, "Courier New", monospace;
  font-size: 0.9em;
}

.markdown-body :deep(pre) {
  padding: 1vh 1vw;
  overflow: auto;
  background: #f7f7f7;
  border-radius: 0.6vmax;
}

.markdown-body :deep(pre code) {
  padding: 0;
  background: transparent;
}

.markdown-body :deep(a) {
  color: var(--app-color-primary);
  word-break: break-all;
}

.markdown-body :deep(table) {
  width: 100%;
  margin: 1.5vh 0;
  border-collapse: collapse;
}

.markdown-body :deep(th),
.markdown-body :deep(td) {
  padding: 0.7vh 0.8vw;
  border: 1px solid var(--app-color-blue-light-4);
  text-align: left;
}

/* 相关事件 */
.events-tab {
  display: flex;
  flex-direction: column;
  gap: 1vh;
}

.related-event {
  display: flex;
  align-items: center;
  gap: 1vw;
  border: 1px solid var(--app-color-blue-light-4);
  border-radius: 0.8vmax;
  padding: 1.2vh 1vw;
  cursor: pointer;
  transition: background 0.15s, border-color 0.15s;
}
.related-event:hover {
  background: #f7f9ff;
  border-color: var(--app-color-primary);
}

.event-tag {
  font-size: 0.9vmax;
  padding: 0 0.5vw;
  border-radius: 0.4vmax;
  flex-shrink: 0;
}

.related-event-title {
  font-size: 1vmax;
  font-weight: bold;
}

.related-event-meta {
  font-size: 0.9vmax;
  color: var(--app-color-gray);
  margin-top: 0.2vh;
}

/* 涉及竞品 */
.competitors-tab {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 1vw;
}

.competitor-card {
  border: 1px solid var(--app-color-blue-light-4);
  border-radius: 0.8vmax;
  padding: 1.5vh 1vw;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.6vh;
  cursor: pointer;
  transition: background 0.15s, border-color 0.15s;
}
.competitor-card:hover {
  background: #f7f9ff;
  border-color: var(--app-color-primary);
}

.competitor-logo {
  width: 3.5vmax;
  height: 3.5vmax;
  min-width: 36px;
  min-height: 36px;
  border-radius: 0.8vmax;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1.4vmax;
  font-weight: bold;
}

.competitor-name {
  font-size: 1vmax;
  font-weight: bold;
}

.competitor-changes {
  font-size: 0.9vmax;
  color: var(--app-color-gray);
}

/* AI 分析过程 */
.ai-tab {
  padding: 1vh 0.5vw;
}

.ai-step-title {
  font-size: 1.1vmax;
  font-weight: bold;
}

.ai-step-desc {
  font-size: 1vmax;
  color: var(--app-color-gray);
  margin-top: 0.4vh;
}

.main-empty {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
}
</style>
