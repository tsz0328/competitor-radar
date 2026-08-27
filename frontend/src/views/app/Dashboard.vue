<script setup lang="ts">
import { onMounted } from "vue";
import TrendChart from "@/components/Charts/TrendChart.vue";
import { useTrendStore } from "@/stores/trend";
import { useEventStore } from "@/stores/event";
import { Monitor, List, Document, Warning } from "@element-plus/icons-vue";
import Openai from "@/components/Icons/Openai.vue";

const trendStore = useTrendStore();
const eventStore = useEventStore();

onMounted(() => {
  trendStore.loadTrend();
  eventStore.loadEvents();
});
</script>
<template>
  <div class="dashboard">
    <!-- 头部 -->
    <header class="header">
      <div class="header-left">
        <div class="title">早上好，用户</div>
        <div class="subtitle">这是您今天的竞品情报概览</div>
      </div>
      <div class="header-right">
        <el-date-picker
          class="header-date"
          type="date"
          placeholder="选择日期"
        />
      </div>
    </header>

    <!-- 统计卡片 -->
    <section class="stat-cards">
      <div class="stat-card card">
        <div class="stat-card-content">
          <div class="stat-card-title">监控竞品</div>
          <div class="stat-card-value">12</div>
          <div class="stat-card-desc">+2 本周新增</div>
        </div>
        <div class="stat-card-icon icon-blue">
          <el-icon>
            <Monitor />
          </el-icon>
        </div>
      </div>
      <div class="stat-card card">
        <div class="stat-card-content">
          <div class="stat-card-title">新增事件</div>
          <div class="stat-card-value">28</div>
          <div class="stat-card-desc">+12% 较上周</div>
        </div>
        <div class="stat-card-icon icon-purple">
          <el-icon>
            <List />
          </el-icon>
        </div>
      </div>
      <div class="stat-card card">
        <div class="stat-card-content">
          <div class="stat-card-title">AI 报告</div>
          <div class="stat-card-value">6</div>
          <div class="stat-card-desc">+2 本周新增</div>
        </div>
        <div class="stat-card-icon icon-green">
          <el-icon>
            <Document />
          </el-icon>
        </div>
      </div>
      <div class="stat-card card">
        <div class="stat-card-content">
          <div class="stat-card-title">风险提醒</div>
          <div class="stat-card-value">3</div>
          <div class="stat-card-desc">+1 本周新增</div>
        </div>
        <div class="stat-card-icon icon-orange">
          <el-icon>
            <Warning />
          </el-icon>
        </div>
      </div>
    </section>

    <!-- 图表和洞察 -->
    <section class="charts">
      <div class="chart card">
        <header class="card-head">
          <div class="card-title">竞品动态趋势</div>
          <el-select
            class="card-select"
            :model-value="trendStore.range"
            @change="trendStore.setRange"
          >
            <el-option label="近7天" value="7" />
            <el-option label="近30天" value="30" />
            <el-option label="近90天" value="90" />
          </el-select>
        </header>
        <trend-chart :data="trendStore.trendData" height="100%" />
      </div>
      <div class="insight card">
        <header class="card-head">
          <div class="card-title">最新 AI 洞察</div>
          <el-button class="card-button" type="text">查看更多</el-button>
        </header>
        <div class="insight-main">
          <div class="insight-content">
            <div class="insight-icon">
              <Openai size="1em" />
            </div>
            <div class="insight-text">
              <div class="insight-title">OpenAI 调整API定价策略</div>
              <div class="insight-desc">
                部分模型价格下调20%，可能影响开发者生态和部分市场。
              </div>
              <div class="insight-date">2小时前</div>
            </div>
          </div>
          <div class="insight-content">
            <div class="insight-icon">
              <Openai size="1em" />
            </div>
            <div class="insight-text">
              <div class="insight-title">OpenAI 调整API定价策略</div>
              <div class="insight-desc">
                部分模型价格下调20%，可能影响开发者生态和部分市场。
              </div>
              <div class="insight-date">2小时前</div>
            </div>
          </div>
          <div class="insight-content">
            <div class="insight-icon">
              <Openai size="1em" />
            </div>
            <div class="insight-text">
              <div class="insight-title">OpenAI 调整API定价策略</div>
              <div class="insight-desc">
                部分模型价格下调20%，可能影响开发者生态和部分市场。
              </div>
              <div class="insight-date">2小时前</div>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- 最新事件 -->
    <section class="latest-events">
      <div class="card">
        <header class="card-head">
          <div class="card-title">最新情报事件</div>
          <el-button class="card-button" type="text">查看更多</el-button>
        </header>
        <!-- 事件列表 -->
        <div class="new-events-main" v-loading="eventStore.loading">
          <div
            class="timeline-item"
            v-for="(event, index) in eventStore.events"
            :key="index"
            :class="{ 'is-first': index === 0 }"
          >
            <div class="timeline-time">{{ event.time }}</div>
            <div class="timeline-track">
              <div class="timeline-dot"></div>
            </div>
            <div class="timeline-body">
              <div
                class="event-icon"
                :style="{
                  backgroundColor: event.iconBg,
                  color: event.iconColor,
                }"
              >
                {{ event.iconText }}
              </div>
              <div>
                <div class="event-header">
                  <div class="event-title">{{ event.title }}</div>
                  <div class="event-tag" :class="event.tagType">
                    {{ event.tag }}
                  </div>
                </div>
                <div class="event-desc">{{ event.desc }}</div>
                <div class="event-source">
                  来源：{{ event.source }}
                  <el-button class="event-detail" type="text"
                    >查看详情</el-button
                  >
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>
<style scoped>
.dashboard {
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
}

.title {
  font-size: 1.5vmax;
  font-weight: bold;
}

.subtitle {
  font-size: 1vmax;
  color: var(--app-color-gray);
}

.header-right {
  display: flex;
  align-items: center;
  width: 12vw;
}

.stat-cards {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 3vw;
}

.card {
  background-color: var(--app-color-white);
  border-radius: 1vmax;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.1);
}

.stat-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1vh 1vw;
}

.stat-card-content {
  display: flex;
  flex-direction: column;
}

.stat-card-title {
  font-size: 1.2vmax;
  font-weight: bold;
}

.stat-card-value {
  font-size: 1.5vmax;
  font-weight: bold;
}

.stat-card-desc {
  font-size: 1vmax;
  color: var(--app-color-gray);
}

.stat-card-icon {
  width: 4vmax;
  height: 4vmax;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 2vmax;
}

.icon-blue {
  background-color: var(--app-color-blue-light-4);
  color: var(--app-color-blue);
}

.icon-purple {
  background-color: var(--app-color-purple-light-4);
  color: var(--app-color-purple);
}

.icon-green {
  background-color: var(--app-color-green-light-4);
  color: var(--app-color-green);
}

.icon-orange {
  background-color: var(--app-color-orange-light-4);
  color: var(--app-color-orange);
}

.card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1vh 1vw;
  font-size: 1.2vmax;
}

.card-title {
  font-weight: bold;
}

.card-select {
  width: 8vw;
  min-width: 90px;
}

.card-button {
  font-size: 1vmax;
  height: auto;
}
.new-events-main {
  padding: 1vh 1vw;
  display: flex;
  flex-direction: column;
}
.timeline-item {
  display: flex;
  align-items: stretch;
  min-height: 80px;
  gap: 1vw;
}
.timeline-time {
  width: 5vw;
  min-width: 60px;
  flex-shrink: 0;
  text-align: right;
  font-size: 1vmax;
  color: var(--app-color-gray);
  white-space: nowrap;  /* 防止时间换行导致宽度不一致 */
}
.timeline-track {
  width: 2px;
  background-color: #e4e7ed;
  position: relative;
  flex-shrink: 0;
}
.timeline-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background-color: #c0c4cc;
  position: absolute;
  left: 50%;
  top: 3vmax;
  transform: translateX(-50%);
}
/* 首圆点加大或变色 */
.timeline-item.is-first .timeline-dot {
  width: 12px;
  height: 12px;
  background-color: #5b6fff;
  box-shadow: 0 0 0 3px rgba(91, 111, 255, 0.2);
}
.timeline-body {
  flex: 1;
  display: flex;
  gap: 1vw;
  align-items: center;
  padding: 1vh 1vw;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.1);
  border-radius: 1vmax;
  margin-bottom: 1vh;
}
.timeline-item:last-child .timeline-body {
  margin-bottom: 0;
}
.event-header {
  display: flex;
  align-items: center;
  gap: 0.8vw;
}
.event-icon {
  width: 4vmax;
  height: 4vmax;
  min-width: 32px;
  min-height: 32px;
  border-radius: 0.6vmax;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 3vmax;
  font-weight: bold;
  flex-shrink: 0;
}
.event-title {
  font-size: 1.2vmax;
  font-weight: bold;
}
.event-tag {
  font-size: 1vmax;
  padding: 0 0.5vw;
  border-radius: 0.4vmax;
  flex-shrink: 0;
}
.tag-new {
  background-color: #e6eaff;
  color: #5b6fff;
}
.tag-price {
  background-color: #fff1f0;
  color: #ff4d4f;
}
.tag-update {
  background-color: #fff7e6;
  color: #fa8c16;
}
.event-desc {
  font-size: 1vmax;
}
.event-source {
  font-size: 0.9vmax;
  color: var(--app-color-gray);
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.event-detail {
  font-size: 0.9vmax;
  height: auto;
}
.insight-main {
  display: flex;
  flex-direction: column;
  gap: 1vh;
  padding: 1vh 1vw;
}

.insight-content {
  display: flex;
  align-items: center;
  gap: 1vw;
  border-radius: 1vmax;
  box-shadow: 0 1px 10px rgba(0, 0, 0, 0.1);
  padding: 1vh 1vw;
}

.insight-icon {
  width: 4vmax;
  height: 4vmax;
  border-radius: 1vmax;
  background-color: var(--app-color-blue-light-4);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 3vmax;
  flex-shrink: 0;
}

.insight-title {
  font-size: 1.2vmax;
  font-weight: bold;
}

.insight-desc {
  font-size: 1vmax;
}

.insight-date {
  font-size: 1vmax;
  color: var(--app-color-gray);
}

.charts {
  display: grid;
  grid-template-columns: 3fr 2fr;
  gap: 3vw;
}

.chart {
  display: flex;
  flex-direction: column;
}

.insight {
  display: flex;
  flex-direction: column;
}
</style>
