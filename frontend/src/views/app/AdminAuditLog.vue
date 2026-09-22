<script setup lang="ts">
import { onMounted, ref } from "vue";
import { Refresh } from "@element-plus/icons-vue";
import { listAuditLogs, type AuditLog } from "@/api/admin";

const loading = ref(false);
const rows = ref<AuditLog[]>([]);
const total = ref(0);
const page = ref(1);
const pageSize = ref(10);
const action = ref("");
const keyword = ref("");

/** 动作筛选选项：value 与后端 action 字段对齐 */
const ACTION_OPTIONS = [
  { label: "全部操作", value: "" },
  { label: "修改用户", value: "update_user" },
  { label: "删除用户", value: "delete_user" },
  { label: "修改系统设置", value: "update_system_settings" },
  { label: "发布公告", value: "create_announcement" },
  { label: "更新公告", value: "update_announcement" },
  { label: "上传竞品图标", value: "upload_competitor_icon" },
  { label: "刷新竞品图标", value: "refresh_competitor_icon" },
];

const ACTION_LABELS: Record<string, string> = {
  update_user: "修改用户",
  delete_user: "删除用户",
  update_system_settings: "修改系统设置",
  create_announcement: "发布公告",
  update_announcement: "更新公告",
  upload_competitor_icon: "上传竞品图标",
  refresh_competitor_icon: "刷新竞品图标",
};

function actionLabel(value: string) {
  return ACTION_LABELS[value] ?? value;
}

async function load() {
  loading.value = true;
  try {
    const res = await listAuditLogs({
      page: page.value,
      page_size: pageSize.value,
      action: action.value || undefined,
      keyword: keyword.value.trim() || undefined,
    });
    rows.value = res.items;
    total.value = res.total;
  } catch {
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

onMounted(load);
</script>
<template>
  <div class="admin-audit-log">
    <header class="header">
      <div>
        <div class="title">审计日志</div>
        <div class="subtitle">管理员的敏感操作留痕（仅管理员可见）</div>
      </div>
      <div class="actions">
        <el-button :icon="Refresh" @click="load">刷新</el-button>
      </div>
    </header>

    <section class="card filter-card">
      <el-select
        v-model="action"
        class="filter-item"
        placeholder="筛选操作类型"
        clearable
        @change="onSearch"
      >
        <el-option
          v-for="opt in ACTION_OPTIONS"
          :key="opt.value"
          :label="opt.label"
          :value="opt.value"
        />
      </el-select>
      <el-input
        v-model="keyword"
        class="filter-item filter-input"
        placeholder="搜索操作人 / 目标类型 / 详情"
        clearable
        @keyup.enter="onSearch"
        @clear="onSearch"
      />
      <el-button type="primary" @click="onSearch">搜索</el-button>
    </section>

    <section class="card table-card">
      <header class="card-head">
        <span class="card-title">日志列表</span>
        <span class="card-hint">共 {{ total }} 条</span>
      </header>
      <el-table :data="rows" v-loading="loading" size="large">
        <el-table-column label="时间" prop="created_at" min-width="160" />
        <el-table-column
          label="操作人"
          prop="admin_username"
          min-width="140"
          show-overflow-tooltip
        />
        <el-table-column label="动作" min-width="130">
          <template #default="{ row }">
            <span>{{ actionLabel(row.action) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="目标类型" min-width="150" show-overflow-tooltip>
          <template #default="{ row }">
            <span v-if="row.target_type">{{ row.target_type }}</span>
            <span v-else class="muted">-</span>
          </template>
        </el-table-column>
        <el-table-column label="目标 ID" width="100" align="right">
          <template #default="{ row }">
            <span v-if="row.target_id !== null">{{ row.target_id }}</span>
            <span v-else class="muted">-</span>
          </template>
        </el-table-column>
        <el-table-column label="详情" min-width="260" show-overflow-tooltip>
          <template #default="{ row }">
            <span v-if="row.detail">{{ row.detail }}</span>
            <span v-else class="muted">-</span>
          </template>
        </el-table-column>
      </el-table>

      <el-empty v-if="!loading && rows.length === 0" description="没有匹配的日志" />

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
.admin-audit-log {
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
  flex-wrap: wrap;
}
.filter-item {
  width: 200px;
}
.filter-input {
  width: 280px;
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

.muted {
  color: var(--app-color-gray);
}

.pagination {
  display: flex;
  justify-content: flex-end;
  padding-top: 0.5vh;
}
</style>