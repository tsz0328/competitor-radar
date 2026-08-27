<script setup lang="ts">
import { ref, computed, onMounted } from "vue";
import { useCompetitorStore } from "@/stores/competitor";
import type { CompetitorItem } from "@/types/competitor";
import {
  Search,
  Grid,
  List as ListIcon,
  Edit,
  More,
  Delete,
} from "@element-plus/icons-vue";

const store = useCompetitorStore();

const keyword = ref("");
const statusFilter = ref("");
const categoryFilter = ref("");
const viewMode = ref<"list" | "grid">("list");
const page = ref(1);
const pageSize = ref(10);

onMounted(() => {
  store.loadCompetitors();
});

const statusOptions = [
  { label: "全部状态", value: "" },
  { label: "监控中", value: "监控中" },
  { label: "监控异常", value: "监控异常" },
  { label: "已暂停", value: "已暂停" },
];

const categoryOptions = computed(() => {
  const set = new Set(store.competitors.map((c) => c.category));
  return [
    { label: "全部类型", value: "" },
    ...Array.from(set).map((c) => ({ label: c, value: c })),
  ];
});

const filteredList = computed(() => {
  return store.competitors.filter((item) => {
    const k = keyword.value.trim().toLowerCase();
    const matchKeyword =
      !k ||
      item.name.toLowerCase().includes(k) ||
      item.domain.toLowerCase().includes(k);
    const matchStatus =
      !statusFilter.value || item.status === statusFilter.value;
    const matchCategory =
      !categoryFilter.value || item.category === categoryFilter.value;
    return matchKeyword && matchStatus && matchCategory;
  });
});

const total = computed(() => filteredList.value.length);

const pagedList = computed(() => {
  const start = (page.value - 1) * pageSize.value;
  return filteredList.value.slice(start, start + pageSize.value);
});

function categoryClass(item: CompetitorItem) {
  return `tag-${item.categoryType}`;
}

function statusClass(item: CompetitorItem) {
  return `status-${item.statusType}`;
}
</script>

<template>
  <div class="competitor">
    <!-- 顶部工具栏 -->
    <div class="toolbar">
      <!-- 左侧筛选 -->
      <div class="toolbar-left">
        <el-input
          v-model="keyword"
          placeholder="搜索竞品名称或关键词..."
          class="search-input"
          :prefix-icon="Search"
          clearable
        />
        <el-select
          v-model="statusFilter"
          placeholder="全部状态"
          class="filter-select"
          clearable
        >
          <el-option
            v-for="opt in statusOptions"
            :key="opt.value"
            :label="opt.label"
            :value="opt.value"
          />
        </el-select>
        <el-select
          v-model="categoryFilter"
          placeholder="全部类型"
          class="filter-select"
          clearable
        >
          <el-option
            v-for="opt in categoryOptions"
            :key="opt.value"
            :label="opt.label"
            :value="opt.value"
          />
        </el-select>
      </div>
      <!-- 右侧按钮 -->
      <div class="toolbar-right">
        <el-button-group class="view-switch">
          <el-button
            :type="viewMode === 'list' ? 'primary' : 'default'"
            @click="viewMode = 'list'"
          >
            <el-icon><ListIcon /></el-icon>
          </el-button>
          <el-button
            :type="viewMode === 'grid' ? 'primary' : 'default'"
            @click="viewMode = 'grid'"
          >
            <el-icon><Grid /></el-icon>
          </el-button>
        </el-button-group>
        <el-button type="primary">新增竞品</el-button>
      </div>
    </div>

    <!-- 列表视图 -->
    <div
      v-if="viewMode === 'list'"
      v-loading="store.loading"
      class="table-wrap"
    >
      <el-table :data="pagedList" height="100%" style="width: 100%">
        <el-table-column label="竞品信息" min-width="260">
          <template #default="{ row }">
            <div class="competitor-info">
              <el-avatar
                :src="row.logoUrl"
                :size="44"
                shape="square"
                class="logo"
              />
              <div class="competitor-meta">
                <div class="competitor-name">
                  {{ row.name }}
                  <el-tag
                    :class="categoryClass(row)"
                    size="small"
                    effect="light"
                    class="category-tag"
                    >{{ row.category }}</el-tag
                  >
                </div>
                <div class="competitor-desc">{{ row.desc }}</div>
                <div class="competitor-domain">{{ row.domain }}</div>
              </div>
            </div>
          </template>
        </el-table-column>

        <el-table-column label="监控页面" min-width="180">
          <template #default="{ row }">
            <div class="pages-list">
              <span v-for="(p, idx) in row.pages" :key="idx" class="page-tag">{{
                p
              }}</span>
              <span v-if="row.extraPages > 0" class="page-more"
                >+{{ row.extraPages }}</span
              >
            </div>
          </template>
        </el-table-column>

        <el-table-column label="最近抓取" min-width="150">
          <template #default="{ row }">
            <div class="last-fetch">
              <div class="last-fetch-ago">{{ row.lastFetchAgo }}</div>
              <div class="last-fetch-time">{{ row.lastFetchTime }}</div>
            </div>
          </template>
        </el-table-column>

        <el-table-column label="状态" min-width="140">
          <template #default="{ row }">
            <div class="status">
              <el-tag
                :class="statusClass(row)"
                size="small"
                effect="light"
                class="status-tag"
              >
                <span class="status-dot" :class="row.statusType" />
                {{ row.status }}
              </el-tag>
              <div class="status-desc">{{ row.statusDesc }}</div>
            </div>
          </template>
        </el-table-column>

        <el-table-column label="最近变化" min-width="120">
          <template #default="{ row }">
            <div class="changes">
              <div class="changes-count">{{ row.changes }} 条</div>
              <div class="changes-today" :class="{ up: row.todayChanges > 0 }">
                今天 {{ row.todayChanges > 0 ? "+" : "" }}{{ row.todayChanges }}
              </div>
            </div>
          </template>
        </el-table-column>

        <el-table-column label="操作" min-width="120" fixed="right">
          <template #default="{ row }: { row: CompetitorItem }">
            <div class="actions">
              <el-button link type="primary" :icon="Edit" />
              <el-switch
                v-model="row.enabled"
                @change="store.toggleMonitor(row.id)"
                inline-prompt
                active-text="开启"
                inactive-text="关闭"
              />
              <el-button link type="danger" :icon="Delete" />
            </div>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 网格视图 -->
    <div v-else v-loading="store.loading" class="grid-wrap">
      <el-row :gutter="16">
        <el-col
          v-for="item in pagedList"
          :key="item.id"
          :xs="24"
          :sm="12"
          :md="8"
          :lg="6"
        >
          <div class="competitor-card">
            <div class="card-header">
              <el-avatar
                :src="item.logoUrl"
                :size="48"
                shape="square"
                class="logo"
              />
              <div class="card-title">
                <div class="name">{{ item.name }}</div>
                <el-tag
                  :class="categoryClass(item)"
                  size="small"
                  effect="light"
                  >{{ item.category }}</el-tag
                >
              </div>
            </div>
            <div class="card-desc">{{ item.desc }}</div>
            <div class="card-row">
              <span class="label">最近抓取</span>
              <span>{{ item.lastFetchAgo }}</span>
            </div>
            <div class="card-row">
              <span class="label">状态</span>
              <el-tag :class="statusClass(item)" size="small" effect="light">
                <span class="status-dot" :class="item.statusType" />
                {{ item.status }}
              </el-tag>
            </div>
            <div class="card-row">
              <span class="label">最近变化</span>
              <span
                >{{ item.changes }} 条 / 今天
                {{ item.todayChanges > 0 ? "+" : ""
                }}{{ item.todayChanges }}</span
              >
            </div>
            <div class="card-actions">
              <el-button link type="primary" :icon="Edit" />
              <el-switch
                v-model="item.enabled"
                inline-prompt
                active-text="开启"
                inactive-text="关闭"
                @change="store.toggleMonitor(item.id)"
              />
              <el-button link type="danger" :icon="Delete" />
            </div>
          </div>
        </el-col>
      </el-row>
    </div>

    <!-- 分页 -->
    <div class="pagination-bar">
      <span class="total-text">共 {{ total }} 条竞品</span>
      <el-pagination
        v-model:current-page="page"
        v-model:page-size="pageSize"
        :page-sizes="[10, 20, 50]"
        layout="prev, pager, next, sizes"
        :total="total"
        background
      />
    </div>
  </div>
</template>

<style scoped>
.competitor {
  height: 100%;
  padding: 2vh 2vw;
  display: flex;
  flex-direction: column;
  gap: 2vh;
}

/* 工具栏 */
.toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1vw;
}
.toolbar-left {
  display: flex;
  align-items: center;
  gap: 1vw;
}
.search-input {
  width: 20vw;
}
.filter-select {
  width: 10vw;
}
.toolbar-right {
  display: flex;
  align-items: center;
  gap: 0.8vw;
}
.view-switch .el-button {
  padding: 0.6vh 0.8vw;
}

/* 列表容器 */
.table-wrap {
  flex: 1;
  min-height: 0;
  background: var(--app-color-white);
  border-radius: 1vmax;
  padding: 1vh 1vw;
}
.table-wrap :deep(.el-table) {
  --el-table-border-color: transparent;
  --el-table-row-hover-bg-color: var(--app-color-blue-light-5);
}

/* 竞品信息列 */
.competitor-info {
  display: flex;
  align-items: center;
  gap: 0.8vw;
}
.logo {
  border-radius: 0.6vmax;
  background: var(--app-color-blue-light-5);
  flex-shrink: 0;
}
.competitor-meta {
  display: flex;
  flex-direction: column;
  gap: 0.4vh;
}
.competitor-name {
  display: flex;
  align-items: center;
  gap: 0.5vw;
  font-weight: 600;
  font-size: 1.05vmax;
}
.category-tag {
  border-radius: 100vmax;
  border: none;
}
.competitor-desc {
  font-size: 0.9vmax;
  color: var(--app-text-color-secondary);
}
.competitor-domain {
  font-size: 0.8vmax;
  color: var(--app-text-color-placeholder);
}

/* 分类标签颜色 */
.tag-saas {
  background: var(--app-color-blue-light-4);
  color: var(--app-color-blue-dark-2);
}
.tag-ai {
  background: var(--app-color-purple-light-4);
  color: var(--app-color-purple-dark-2);
}
.tag-brand {
  background: var(--app-color-orange-light-4);
  color: var(--app-color-orange-dark-2);
}
.tag-ecommerce {
  background: var(--app-color-red-light-4);
  color: var(--app-color-red-dark-2);
}

/* 监控页面 */
.pages-list {
  display: flex;
  flex-wrap: wrap;
  gap: 0.4vw;
}
.page-tag {
  padding: 0.3vh 0.6vw;
  background: var(--app-color-blue-light-5);
  color: var(--app-text-color-secondary);
  border-radius: 0.4vmax;
  font-size: 0.85vmax;
}
.page-more {
  padding: 0.3vh 0.6vw;
  color: var(--app-text-color-placeholder);
  font-size: 0.85vmax;
}

/* 频率 / 抓取 / 变化 */
.last-fetch-ago,
.changes-count {
  font-size: 0.95vmax;
  color: var(--app-text-color-regular);
}
.frequency-sub,
.last-fetch-time,
.status-desc {
  font-size: 0.8vmax;
  color: var(--app-text-color-placeholder);
  margin-top: 0.3vh;
}

/* 状态 */
.status {
  display: flex;
  flex-direction: column;
  gap: 0.3vh;
}
.status-tag {
  display: inline-flex;
  align-items: center;
  gap: 0.35vw;
  border-radius: 100vmax;
  border: none;
  width: fit-content;
}
.status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
}
.status-dot.success {
  background: var(--el-color-success);
}
.status-dot.warning {
  background: var(--el-color-warning);
}
.status-dot.info {
  background: var(--app-text-color-placeholder);
}
.status-success {
  background: var(--app-color-green-light-5);
  color: var(--app-color-green-dark-2);
}
.status-warning {
  background: var(--app-color-orange-light-5);
  color: var(--app-color-orange-dark-2);
}
.status-info {
  background: var(--app-color-blue-light-5);
  color: var(--app-color-blue-dark-2);
}

/* 变化数 */
.changes-today {
  font-size: 0.85vmax;
  color: var(--app-text-color-placeholder);
  margin-top: 0.3vh;
}
.changes-today.up {
  color: var(--el-color-danger);
}

/* 操作 */
.actions {
  display: flex;
  align-items: center;
  gap: 0.6vw;
}
.actions .el-button {
  font-size: 1.5vmax;
}
/* 分页 */
.pagination-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-shrink: 0;
}
.total-text {
  font-size: 0.9vmax;
  color: var(--app-text-color-secondary);
}

/* 网格视图 */
.grid-wrap {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 0.5vh 0;
}
.competitor-card {
  background: var(--app-color-white);
  border-radius: 1vmax;
  padding: 1.5vh 1vw;
  margin-bottom: 1.5vh;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.05);
}
.card-header {
  display: flex;
  align-items: center;
  gap: 0.8vw;
  margin-bottom: 1vh;
}
.card-title {
  display: flex;
  flex-direction: column;
  gap: 0.4vh;
}
.card-title .name {
  font-weight: 600;
  font-size: 1.05vmax;
}
.card-desc {
  font-size: 0.9vmax;
  color: var(--app-text-color-secondary);
  margin-bottom: 1vh;
}
.card-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 0.9vmax;
  margin-bottom: 0.6vh;
}
.card-row .label {
  color: var(--app-text-color-placeholder);
}
.card-actions {
  display: flex;
  justify-content: flex-end;
  gap: 0.5vw;
  margin-top: 1vh;
}
.card-actions .el-button {
  font-size: 1.5vmax;
}
</style>
