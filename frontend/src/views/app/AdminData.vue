<script setup lang="ts">
/**
 * 平台数据（仅管理员）：情报事件 / 周度报告 / 抓取日志三个 tab 的跨用户列表。
 * 总览页三张计数卡（情报事件 / 周度报告 / 抓取次数）点击带 ?tab= 跳到这里，
 * 菜单「平台数据」进入时默认落在情报事件 tab。
 */
import { computed, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { Refresh } from "@element-plus/icons-vue";
import {
  listAdminEvents,
  listAdminReports,
  listAdminCrawlLogs,
  type AdminEvent,
  type AdminReport,
  type AdminCrawlLog,
} from "@/api/admin";

type TabKey = "events" | "reports" | "crawls";
const TABS: { key: TabKey; label: string }[] = [
  { key: "events", label: "情报事件" },
  { key: "reports", label: "周度报告" },
  { key: "crawls", label: "抓取日志" },
];
function isTabKey(v: unknown): v is TabKey {
  return TABS.some((t) => t.key === v);
}

const route = useRoute();
const router = useRouter();

const activeTab = ref<TabKey>(isTabKey(route.query.tab) ? route.query.tab : "events");
const loading = ref(false);
const rows = ref<AdminEvent[] | AdminReport[] | AdminCrawlLog[]>([]);
const total = ref(0);
const keyword = ref("");
const page = ref(1);
const pageSize = ref(10);
/** 平台数据·周度报告：是否一并展示软删（回收站）报告，默认只看有效 */
const includeDeleted = ref(false);

const filterPlaceholder = computed(() => {
  if (activeTab.value === "events") return "搜索事件标题";
  if (activeTab.value === "reports") return "搜索报告标题";
  return "搜索竞品名 / 监控源";
});

async function load() {
  loading.value = true;
  try {
    const params = {
      keyword: keyword.value.trim() || undefined,
      page: page.value,
      page_size: pageSize.value,
    };
    if (activeTab.value === "events") {
      const res = await listAdminEvents(params);
      rows.value = res.items;
      total.value = res.total;
    } else if (activeTab.value === "reports") {
      const res = await listAdminReports({
        ...params,
        include_deleted: includeDeleted.value,
      });
      rows.value = res.items;
      total.value = res.total;
    } else {
      const res = await listAdminCrawlLogs(params);
      rows.value = res.items;
      total.value = res.total;
    }
  } catch {
    rows.value = [];
    total.value = 0;
    // 错误提示由 request.ts 统一弹出
  } finally {
    loading.value = false;
  }
}

function onSearch() {
  page.value = 1;
  load();
}

function onPageChange(p: number) {
  page.value = p;
  load();
}

function onSizeChange(size: number) {
  pageSize.value = size;
  page.value = 1;
  load();
}

function onToggleDeleted() {
  page.value = 1;
  load();
}

/** 切 tab：重置筛选与页码，并把 tab 写回 URL（可分享 / 刷新保持） */
function resetAndLoad() {
  keyword.value = "";
  page.value = 1;
  load();
}

function onTabChange(name: TabKey) {
  // 注意：el-tabs 会先通过 v-model 更新 activeTab，再触发 tab-change，
  // 因此这里不能再判 name === activeTab 提前返回，否则切 tab 永远不重新加载。
  activeTab.value = name;
  router.replace({ query: { ...route.query, tab: name } });
  resetAndLoad();
}

/** 外部跳转（总览卡片点进来）带 ?tab= 时跟随 */
watch(
  () => route.query.tab,
  (tab) => {
    const key = isTabKey(tab) ? tab : "events";
    if (key !== activeTab.value) {
      activeTab.value = key;
      resetAndLoad();
    }
  },
);

// ---- 展示映射：后端给原始值，这里转中文标签 ----

const PRIORITY_LABELS: Record<string, string> = { high: "高", mid: "中", low: "低" };
const REPORT_TYPE_LABELS: Record<string, string> = { weekly: "周报", monthly: "月报" };

function crawlStatus(row: AdminCrawlLog): { label: string; type: "success" | "danger" | "info" } {
  if (row.status === "success") return { label: "成功", type: "success" };
  if (row.status === "failed") return { label: "失败", type: "danger" };
  return { label: "跳过", type: "info" };
}

function crawlTrigger(row: AdminCrawlLog): string {
  if (row.trigger === "scheduler") return "定时";
  return "手动";
}

function crawlOutcome(row: AdminCrawlLog): string {
  if (!row.changed) return "无变化";
  return row.event_created ? "有变化 · 产出事件" : "有变化";
}

function ownerLabel(owner: string): string {
  return owner || "（未知）";
}

onMounted(load);
</script>
<template>
  <div class="admin-data">
    <header class="header">
      <div>
        <div class="title">平台数据</div>
        <div class="subtitle">全部用户的情报事件、周度报告与抓取日志</div>
      </div>
      <div class="actions">
        <el-button :icon="Refresh" :loading="loading" @click="load">刷新</el-button>
      </div>
    </header>

    <el-tabs v-model="activeTab" class="card tabs-card" @tab-change="onTabChange">
      <el-tab-pane
        v-for="tab in TABS"
        :key="tab.key"
        :label="tab.label"
        :name="tab.key"
      />
    </el-tabs>

    <section class="card filter-card">
      <el-input
        v-model="keyword"
        class="filter-item"
        :placeholder="filterPlaceholder"
        clearable
        @keyup.enter="onSearch"
        @clear="onSearch"
      />
      <el-button type="primary" @click="onSearch">搜索</el-button>
      <el-switch
        v-if="activeTab === 'reports'"
        v-model="includeDeleted"
        active-text="含已删除"
        @change="onToggleDeleted"
      />
    </section>

    <section class="card table-card">
      <header class="card-head">
        <span class="card-title">{{ TABS.find((t) => t.key === activeTab)?.label }}</span>
        <span class="card-hint">共 {{ total }} 条</span>
      </header>

      <!-- 情报事件 -->
      <el-table v-if="activeTab === 'events'" :data="rows" v-loading="loading" size="large">
        <el-table-column label="标题" min-width="240" show-overflow-tooltip>
          <template #default="{ row }">{{ row.title }}</template>
        </el-table-column>
        <el-table-column label="类型" width="130">
          <template #default="{ row }">
            <el-tag size="small" type="info" effect="light">{{ row.event_type_label }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="竞品" min-width="140" show-overflow-tooltip>
          <template #default="{ row }">{{ row.competitor_name }}</template>
        </el-table-column>
        <el-table-column label="归属用户" min-width="130">
          <template #default="{ row }">{{ ownerLabel(row.owner_username) }}</template>
        </el-table-column>
        <el-table-column label="优先级" width="90" align="center">
          <template #default="{ row }">
            <span :class="`pri pri--${row.priority}`">
              {{ PRIORITY_LABELS[row.priority] || row.priority }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="时间" prop="created_at" width="170" />
      </el-table>

      <!-- 周度报告 -->
      <el-table v-else-if="activeTab === 'reports'" :data="rows" v-loading="loading" size="large">
        <el-table-column label="标题" min-width="240" show-overflow-tooltip>
          <template #default="{ row }">
            <span class="report-title">{{ row.title }}</span>
            <el-tag v-if="row.deleted" size="small" type="info" effect="plain">已删除</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="类型" width="100">
          <template #default="{ row }">
            <el-tag
              size="small"
              :type="row.report_type === 'monthly' ? 'warning' : 'primary'"
              effect="light"
            >
              {{ REPORT_TYPE_LABELS[row.report_type] || row.report_type }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="归属用户" min-width="130">
          <template #default="{ row }">{{ ownerLabel(row.owner_username) }}</template>
        </el-table-column>
        <el-table-column label="统计周期" min-width="200">
          <template #default="{ row }">{{ row.range_start }} ~ {{ row.range_end }}</template>
        </el-table-column>
        <el-table-column label="竞品数" prop="competitor_count" width="90" align="right" />
        <el-table-column label="事件数" prop="event_count" width="90" align="right" />
        <el-table-column label="生成时间" prop="created_at" width="170" />
      </el-table>

      <!-- 抓取日志 -->
      <el-table v-else :data="rows" v-loading="loading" size="large">
        <el-table-column label="竞品" min-width="150" show-overflow-tooltip>
          <template #default="{ row }">{{ row.competitor_name }}</template>
        </el-table-column>
        <el-table-column label="监控源" min-width="150" show-overflow-tooltip>
          <template #default="{ row }">{{ row.source_name }}</template>
        </el-table-column>
        <el-table-column label="状态" width="90" align="center">
          <template #default="{ row }">
            <el-tag size="small" :type="crawlStatus(row).type" effect="light">
              {{ crawlStatus(row).label }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="触发" width="90" align="center">
          <template #default="{ row }">{{ crawlTrigger(row) }}</template>
        </el-table-column>
        <el-table-column label="结果" min-width="160">
          <template #default="{ row }">{{ crawlOutcome(row) }}</template>
        </el-table-column>
        <el-table-column label="耗时" width="100" align="right">
          <template #default="{ row }">{{ row.duration_ms }}ms</template>
        </el-table-column>
        <el-table-column label="归属用户" min-width="130">
          <template #default="{ row }">{{ ownerLabel(row.owner_username) }}</template>
        </el-table-column>
        <el-table-column label="时间" prop="created_at" width="170" />
      </el-table>

      <el-empty
        v-if="!loading && rows.length === 0"
        :description="`暂无${TABS.find((t) => t.key === activeTab)?.label ?? ''}数据`"
      />

      <div v-if="total > 0" class="pagination">
        <el-pagination
          background
          layout="total, sizes, prev, pager, next"
          :total="total"
          :current-page="page"
          :page-size="pageSize"
          :page-sizes="[10, 20, 50, 100]"
          @current-change="onPageChange"
          @size-change="onSizeChange"
        />
      </div>
    </section>
  </div>
</template>
<style scoped>
.card {
  background-color: var(--app-color-white);
  border-radius: 1vmax;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.1);
}
.admin-data {
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

/* tabs 放进白卡片里，与筛选/表格卡片视觉一致 */
.tabs-card {
  padding: 0.6vh 1vw;
}
.tabs-card :deep(.el-tabs__header) {
  margin-bottom: 0;
}
.tabs-card :deep(.el-tabs__item) {
  font-size: 1vmax;
}

.filter-card {
  display: flex;
  align-items: center;
  gap: 1vw;
  padding: 1.2vh 1vw;
}
.filter-item {
  width: 260px;
}

.table-card {
  padding: 1vh 1vw;
  display: flex;
  flex-direction: column;
  gap: 1vh;
}

.card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 2vw;
}
.card-title {
  font-size: 1.1vmax;
  font-weight: bold;
}
.card-hint {
  font-size: 0.9vmax;
  color: var(--app-color-gray);
}

.report-title {
  margin-right: 0.5vw;
}

/* 优先级小圆点（与用户端情报中心同款语义色系） */
.pri {
  display: inline-flex;
  align-items: center;
}
.pri::before {
  content: "";
  width: 0.55vmax;
  height: 0.55vmax;
  border-radius: 50%;
  margin-right: 0.35vw;
  background-color: var(--app-color-gray-light-3, #c0c4cc);
}
.pri--high::before {
  background-color: var(--app-color-danger, #f56c6c);
}
.pri--mid::before {
  background-color: var(--app-color-orange, #e6a23c);
}
.pri--low::before {
  background-color: var(--app-color-gray-light-3, #c0c4cc);
}

.pagination {
  display: flex;
  justify-content: flex-end;
  padding-top: 0.5vh;
}
</style>