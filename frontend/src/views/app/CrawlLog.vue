<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { Refresh } from "@element-plus/icons-vue";
import { clearCrawlLogs, fetchCrawlLogs } from "@/api/crawlLog";
import { useCompetitorStore } from "@/stores/competitor";
import type { CrawlLogItem } from "@/types/crawlLog";

const competitorStore = useCompetitorStore();

// ---- 筛选条件 ----
const statusFilter = ref<string>("");
const triggerFilter = ref<string>("");
const competitorFilter = ref<number | "">("");

const statusOptions = [
  { value: "success", label: "成功" },
  { value: "failed", label: "失败" },
  { value: "skipped", label: "跳过" },
];
const triggerOptions = [
  { value: "manual", label: "手动抓取" },
  { value: "scheduler", label: "定时抓取" },
];
const competitorOptions = computed(() =>
  competitorStore.competitors.map((item) => ({ value: item.id, label: item.name })),
);

// ---- 列表与分页 ----
const loading = ref(false);
const rows = ref<CrawlLogItem[]>([]);
const total = ref(0);
const page = ref(1);
const pageSize = ref(20);

// 类型中文名（与后端 SOURCE_TYPE_REGISTRY 对齐）
const TYPE_LABELS: Record<string, string> = {
  homepage: "官网首页",
  pricing: "定价页",
  changelog: "更新日志",
  blog: "官方博客",
  docs: "帮助文档",
  status: "服务状态",
  rss: "RSS 订阅",
  app_store: "应用商店",
};

const STATUS_META: Record<string, { label: string; tag: string }> = {
  success: { label: "成功", tag: "success" },
  failed: { label: "失败", tag: "danger" },
  skipped: { label: "跳过", tag: "info" },
};

function typeLabel(value: string): string {
  return TYPE_LABELS[value] ?? value;
}

function statusLabel(value: string): string {
  return STATUS_META[value]?.label ?? value;
}

function statusTag(value: string): string {
  return STATUS_META[value]?.tag ?? "info";
}

function triggerLabel(value: string): string {
  return value === "scheduler" ? "定时" : "手动";
}

function formatTime(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  const pad = (n: number) => String(n).padStart(2, "0");
  return (
    `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ` +
    `${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`
  );
}

function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

/** 结果摘要：变化 / 首建 / 生成事件，都没有则留空 */
function resultText(row: CrawlLogItem): string {
  const parts: string[] = [];
  if (row.changed) parts.push("内容变化");
  if (row.firstTime) parts.push("建立基准");
  if (row.eventCreated) parts.push("生成情报");
  return parts.join("、");
}

async function load() {
  loading.value = true;
  try {
    const result = await fetchCrawlLogs({
      page: page.value,
      pageSize: pageSize.value,
      status: statusFilter.value || undefined,
      trigger: triggerFilter.value || undefined,
      competitorId: competitorFilter.value === "" ? undefined : competitorFilter.value,
    });
    rows.value = result.items;
    total.value = result.total;
  } finally {
    loading.value = false;
  }
}

function onFilterChange() {
  page.value = 1;
  load();
}

function resetFilters() {
  statusFilter.value = "";
  triggerFilter.value = "";
  competitorFilter.value = "";
  onFilterChange();
}

async function onClear() {
  try {
    await ElMessageBox.confirm(
      "将删除当前账号的全部抓取日志，且不可恢复。确定清空吗？",
      "清空日志",
      { type: "warning", confirmButtonText: "清空", cancelButtonText: "取消" },
    );
  } catch {
    return; // 用户取消
  }
  await clearCrawlLogs();
  ElMessage.success("日志已清空");
  onFilterChange();
}

onMounted(async () => {
  // 竞品筛选下拉需要竞品列表；列表本身并行加载，互不阻塞
  if (!competitorStore.competitors.length) competitorStore.loadCompetitors();
  await load();
});
</script>
<template>
  <div class="crawl-log">
    <!-- 头部：说明 + 操作 -->
    <header class="header">
      <div>
        <div class="title">抓取日志</div>
        <div class="subtitle">手动与定时抓取的成功、失败、告警统一留痕，保留 30 天</div>
      </div>
      <div class="actions">
        <el-button :icon="Refresh" @click="load">刷新</el-button>
        <el-button type="danger" plain @click="onClear">清空</el-button>
      </div>
    </header>

    <!-- 筛选栏 -->
    <section class="card filter-card">
      <el-select
        v-model="statusFilter"
        class="filter-item"
        placeholder="全部状态"
        clearable
        @change="onFilterChange"
      >
        <el-option
          v-for="opt in statusOptions"
          :key="opt.value"
          :label="opt.label"
          :value="opt.value"
        />
      </el-select>
      <el-select
        v-model="triggerFilter"
        class="filter-item"
        placeholder="全部触发方式"
        clearable
        @change="onFilterChange"
      >
        <el-option
          v-for="opt in triggerOptions"
          :key="opt.value"
          :label="opt.label"
          :value="opt.value"
        />
      </el-select>
      <el-select
        v-model="competitorFilter"
        class="filter-item filter-item--wide"
        placeholder="全部竞品"
        clearable
        filterable
        @change="onFilterChange"
      >
        <el-option
          v-for="opt in competitorOptions"
          :key="opt.value"
          :label="opt.label"
          :value="opt.value"
        />
      </el-select>
      <el-button link type="primary" @click="resetFilters">重置</el-button>
    </section>

    <!-- 日志表格 -->
    <section class="card table-card">
      <el-table :data="rows" v-loading="loading" size="large">
        <el-table-column label="时间" width="170">
          <template #default="{ row }">{{ formatTime(row.createdAt) }}</template>
        </el-table-column>
        <el-table-column label="竞品" prop="competitorName" min-width="120" show-overflow-tooltip />
        <el-table-column label="监控页面" min-width="160" show-overflow-tooltip>
          <template #default="{ row }">
            <span class="page-name">{{ row.sourceName }}</span>
            <span class="page-type">{{ typeLabel(row.sourceType) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="触发" width="80">
          <template #default="{ row }">
            <span class="trigger" :class="`trigger--${row.trigger}`">
              {{ triggerLabel(row.trigger) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="statusTag(row.status)" size="small" effect="light">
              {{ statusLabel(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="结果" min-width="120">
          <template #default="{ row }">
            <span v-if="resultText(row)">{{ resultText(row) }}</span>
            <span v-else class="muted">—</span>
          </template>
        </el-table-column>
        <el-table-column label="HTTP" width="80">
          <template #default="{ row }">
            <span v-if="row.httpStatus" :class="{ 'http-bad': row.httpStatus >= 400 }">
              {{ row.httpStatus }}
            </span>
            <span v-else class="muted">—</span>
          </template>
        </el-table-column>
        <el-table-column label="耗时" width="90">
          <template #default="{ row }">{{ formatDuration(row.durationMs) }}</template>
        </el-table-column>
        <el-table-column
          label="失败原因"
          min-width="200"
          show-overflow-tooltip
        >
          <template #default="{ row }">
            <span v-if="row.error" class="error-text">{{ row.error }}</span>
            <span v-else class="muted">—</span>
          </template>
        </el-table-column>
      </el-table>

      <div v-if="!loading && rows.length === 0" class="empty-hint">
        还没有抓取记录，去竞品管理页「立即抓取」试试
      </div>

      <!-- 分页 -->
      <div class="pagination-bar" v-if="total > 0">
        <span class="total-text">共 {{ total }} 条日志</span>
        <el-pagination
          v-model:current-page="page"
          v-model:page-size="pageSize"
          :total="total"
          :page-sizes="[20, 50, 100]"
          layout="prev, pager, next, sizes"
          background
          @current-change="load"
          @size-change="onFilterChange"
        />
      </div>
    </section>
  </div>
</template>
<style scoped>
.crawl-log {
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
  gap: 2vw;
  flex-wrap: wrap;
}
.title {
  font-size: 1.5vmax;
  font-weight: bold;
}
.subtitle {
  font-size: 1vmax;
  color: var(--app-color-gray);
}
.actions {
  display: flex;
  gap: 0.5vw;
}

.filter-card {
  display: flex;
  align-items: center;
  gap: 1vw;
  padding: 1.2vh 1vw;
}
.filter-item {
  width: 140px;
}
.filter-item--wide {
  width: 200px;
}

.table-card {
  padding: 1vh 1vw;
  display: flex;
  flex-direction: column;
  gap: 1vh;
}

.page-name {
  font-weight: 600;
  margin-right: 0.5vw;
}
.page-type {
  font-size: 0.85vmax;
  color: var(--app-color-gray);
}

.trigger {
  font-size: 0.9vmax;
  padding: 0 0.4vw;
  border-radius: 0.3vmax;
}
.trigger--manual {
  color: var(--app-color-blue);
  background: var(--app-color-blue-light-5);
}
.trigger--scheduler {
  color: var(--app-color-gray);
  background: var(--el-fill-color-light);
}

.muted {
  color: var(--app-color-gray);
}
.http-bad {
  color: var(--app-color-danger);
  font-weight: 600;
}
.error-text {
  color: var(--app-color-danger);
}

.empty-hint {
  text-align: center;
  color: var(--app-color-gray);
  padding: 4vh 0;
}

.pagination-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-top: 1vh;
}
.total-text {
  font-size: 0.95vmax;
  color: var(--app-color-gray);
}
</style>
