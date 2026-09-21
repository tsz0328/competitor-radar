<script setup lang="ts">
import { ref, onMounted } from "vue";
import { useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import { Delete, RefreshLeft } from "@element-plus/icons-vue";
import type { CompetitorItem } from "@/types/competitor";
import type { ReportListItem } from "@/types/report";
import { fetchTrash, purgeCompetitor, restoreCompetitor } from "@/api/competitor";
import { fetchTrashReports, purgeReport, restoreReport } from "@/api/report";
import { useCompetitorStore } from "@/stores/competitor";
import { useReportStore } from "@/stores/report";
import CompetitorLogo from "@/components/CompetitorLogo.vue";

const router = useRouter();
const competitorStore = useCompetitorStore();
const reportStore = useReportStore();

const RETENTION_DAYS = 30;
const activeTab = ref<"competitor" | "report">("competitor");

// 竞品回收站
const competitorLoading = ref(false);
const competitorItems = ref<CompetitorItem[]>([]);
const restoringCompetitorId = ref<number | null>(null);
const purgingCompetitorId = ref<number | null>(null);

// 周报回收站
const reportLoading = ref(false);
const reportItems = ref<ReportListItem[]>([]);
const restoringReportId = ref<number | null>(null);
const purgingReportId = ref<number | null>(null);

async function loadCompetitorTrash() {
  competitorLoading.value = true;
  try {
    competitorItems.value = await fetchTrash();
  } finally {
    competitorLoading.value = false;
  }
}

async function loadReportTrash() {
  reportLoading.value = true;
  try {
    reportItems.value = await fetchTrashReports();
  } finally {
    reportLoading.value = false;
  }
}

function switchTab(tab: string) {
  activeTab.value = tab as "competitor" | "report";
  if (tab === "competitor" && !competitorItems.value.length) loadCompetitorTrash();
  if (tab === "report" && !reportItems.value.length) loadReportTrash();
}

onMounted(loadCompetitorTrash);

function displayDomain(domain: string) {
  const host = (domain || "")
    .replace(/^https?:\/\//i, "")
    .split("/")[0]
    .replace(/^www\./i, "");
  return host || "—";
}

function formatDeletedAt(value?: string | null) {
  if (!value) return "—";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return "—";
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

/** 距离自动清理还剩多少天（按自然日向上取整）；无删除标记或解析失败返回 -1 */
function daysLeft(value?: string | null): number {
  if (!value) return -1;
  const deleted = new Date(value).getTime();
  if (Number.isNaN(deleted)) return -1;
  const msLeft = deleted + RETENTION_DAYS * 86400_000 - Date.now();
  if (msLeft <= 0) return 0;
  return Math.ceil(msLeft / 86400_000);
}

async function handleRestoreCompetitor(item: CompetitorItem) {
  if (restoringCompetitorId.value) return;
  restoringCompetitorId.value = item.id;
  try {
    await restoreCompetitor(item.id);
    await loadCompetitorTrash();
    // 同步刷新竞品管理列表，让用户切回去就能看到恢复的竞品
    await competitorStore.loadCompetitors();
    ElMessage.success(`已恢复「${item.name}」，其历史监控数据已重新连接`);
  } catch {
    // 错误提示由拦截器统一弹出
  } finally {
    restoringCompetitorId.value = null;
  }
}

async function handlePurgeCompetitor(item: CompetitorItem) {
  if (purgingCompetitorId.value) return;
  try {
    await ElMessageBox.confirm(
      `彻底删除「${item.name}」将连同其监控记录、情报事件、历史快照一并清除，不可恢复。`,
      "彻底删除竞品",
      {
        type: "warning",
        confirmButtonText: "彻底删除",
        cancelButtonText: "取消",
        confirmButtonClass: "el-button--danger",
      },
    );
  } catch {
    return; // 用户取消
  }
  purgingCompetitorId.value = item.id;
  try {
    await purgeCompetitor(item.id);
    await loadCompetitorTrash();
    ElMessage.success(`已永久删除「${item.name}」`);
  } catch {
    // 错误提示由拦截器统一弹出
  } finally {
    purgingCompetitorId.value = null;
  }
}

async function handleRestoreReport(item: ReportListItem) {
  if (restoringReportId.value) return;
  restoringReportId.value = item.id;
  try {
    await restoreReport(item.id);
    await loadReportTrash();
    // 同步刷新报告列表，让用户切回去就能看到恢复的报告
    await reportStore.loadReportList();
    ElMessage.success(`已恢复「${item.title}」`);
  } catch {
    // 错误提示由拦截器统一弹出
  } finally {
    restoringReportId.value = null;
  }
}

async function handlePurgeReport(item: ReportListItem) {
  if (purgingReportId.value) return;
  try {
    await ElMessageBox.confirm(
      `彻底删除「${item.title}」将连同其全部内容一并清除，不可恢复。`,
      "彻底删除报告",
      {
        type: "warning",
        confirmButtonText: "彻底删除",
        cancelButtonText: "取消",
        confirmButtonClass: "el-button--danger",
      },
    );
  } catch {
    return; // 用户取消
  }
  purgingReportId.value = item.id;
  try {
    await purgeReport(item.id);
    await loadReportTrash();
    ElMessage.success(`已永久删除「${item.title}」`);
  } catch {
    // 错误提示由拦截器统一弹出
  } finally {
    purgingReportId.value = null;
  }
}

function goManage() {
  router.push({ name: "Competitor" });
}
</script>

<template>
  <div class="trash">
    <div class="toolbar">
      <div>
        <h2 class="page-title">回收站</h2>
        <p class="page-sub">
          已删除的竞品和周报会暂存在这里，保留
          <b>{{ RETENTION_DAYS }}</b>
          天，期间可一键恢复；过期将自动清理。
        </p>
      </div>
      <el-button
        :icon="RefreshLeft"
        @click="activeTab === 'competitor' ? loadCompetitorTrash() : loadReportTrash()"
      >
        刷新
      </el-button>
    </div>

    <el-tabs v-model="activeTab" class="trash-tabs" @tab-change="switchTab">
      <el-tab-pane label="竞品" name="competitor">
        <div v-if="!competitorLoading && competitorItems.length === 0" class="empty-state">
          <el-empty description="回收站里没有已删除的竞品" />
        </div>

        <div v-else v-loading="competitorLoading" class="table-wrap">
          <el-table :data="competitorItems" height="100%" style="width: 100%">
            <el-table-column label="竞品" min-width="240">
              <template #default="{ row }">
                <div class="competitor-info">
                  <CompetitorLogo
                    :name="row.name"
                    :domain="row.domain"
                    :src="row.logoUrl"
                    :size="40"
                  />
                  <div class="competitor-meta">
                    <div class="competitor-name">{{ row.name }}</div>
                    <div class="competitor-domain">{{ displayDomain(row.domain) }}</div>
                  </div>
                </div>
              </template>
            </el-table-column>

            <el-table-column label="分类" min-width="120">
              <template #default="{ row }">{{ row.category || "—" }}</template>
            </el-table-column>

            <el-table-column label="历史变化" min-width="110">
              <template #default="{ row }">
                <span class="changes-count">{{ row.changes }} 条</span>
              </template>
            </el-table-column>

            <el-table-column label="删除时间" min-width="170">
              <template #default="{ row }">
                <span>{{ formatDeletedAt(row.deletedAt) }}</span>
              </template>
            </el-table-column>

            <el-table-column label="剩余可恢复" min-width="130">
              <template #default="{ row }">
                <el-tag
                  v-if="row.deletedAt"
                  :type="daysLeft(row.deletedAt) <= 7 ? 'warning' : 'info'"
                  size="small"
                  effect="light"
                >
                  {{ daysLeft(row.deletedAt) }} 天
                </el-tag>
                <span v-else>—</span>
              </template>
            </el-table-column>

            <el-table-column label="操作" width="200" fixed="right">
              <template #default="{ row }: { row: CompetitorItem }">
                <el-button
                  link
                  type="primary"
                  :icon="RefreshLeft"
                  :loading="restoringCompetitorId === row.id"
                  @click="handleRestoreCompetitor(row)"
                  >恢复</el-button
                >
                <el-button
                  link
                  type="danger"
                  :icon="Delete"
                  :loading="purgingCompetitorId === row.id"
                  @click="handlePurgeCompetitor(row)"
                  >彻底删除</el-button
                >
              </template>
            </el-table-column>
          </el-table>
        </div>
      </el-tab-pane>

      <el-tab-pane label="周报 / 月报" name="report">
        <div v-if="!reportLoading && reportItems.length === 0" class="empty-state">
          <el-empty description="回收站里没有已删除的报告" />
        </div>

        <div v-else v-loading="reportLoading" class="table-wrap">
          <el-table :data="reportItems" height="100%" style="width: 100%">
            <el-table-column label="报告" min-width="280">
              <template #default="{ row }">
                <div class="competitor-info">
                  <div class="report-icon">
                    <el-tag :type="row.type === 'monthly' ? 'success' : 'primary'" size="small">
                      {{ row.typeLabel }}
                    </el-tag>
                  </div>
                  <div class="competitor-meta">
                    <div class="competitor-name">{{ row.title }}</div>
                    <div class="competitor-domain">{{ row.range }}</div>
                  </div>
                </div>
              </template>
            </el-table-column>

            <el-table-column label="生成日期" min-width="120">
              <template #default="{ row }">{{ row.generatedAt }}</template>
            </el-table-column>

            <el-table-column label="删除时间" min-width="170">
              <template #default="{ row }">
                <span>{{ formatDeletedAt(row.deletedAt) }}</span>
              </template>
            </el-table-column>

            <el-table-column label="剩余可恢复" min-width="130">
              <template #default="{ row }">
                <el-tag
                  v-if="row.deletedAt"
                  :type="daysLeft(row.deletedAt) <= 7 ? 'warning' : 'info'"
                  size="small"
                  effect="light"
                >
                  {{ daysLeft(row.deletedAt) }} 天
                </el-tag>
                <span v-else>—</span>
              </template>
            </el-table-column>

            <el-table-column label="操作" width="200" fixed="right">
              <template #default="{ row }: { row: ReportListItem }">
                <el-button
                  link
                  type="primary"
                  :icon="RefreshLeft"
                  :loading="restoringReportId === row.id"
                  @click="handleRestoreReport(row)"
                  >恢复</el-button
                >
                <el-button
                  link
                  type="danger"
                  :icon="Delete"
                  :loading="purgingReportId === row.id"
                  @click="handlePurgeReport(row)"
                  >彻底删除</el-button
                >
              </template>
            </el-table-column>
          </el-table>
        </div>
      </el-tab-pane>
    </el-tabs>

    <div class="foot-note">
      没有要恢复的内容了？
      <el-link type="primary" :underline="false" @click="goManage">返回竞品管理</el-link>
    </div>
  </div>
</template>

<style scoped>
.trash {
  height: 100%;
  padding: 2vh 2vw;
  display: flex;
  flex-direction: column;
  gap: 2vh;
}
.toolbar {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1vw;
}
.page-title {
  margin: 0;
  font-size: 1.4vmax;
  font-weight: 600;
}
.page-sub {
  margin: 0.4vh 0 0;
  font-size: 0.9vmax;
  color: var(--app-text-color-secondary);
  line-height: 1.7;
}
.page-sub b {
  color: var(--app-color-primary);
}
.trash-tabs {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}
.trash-tabs :deep(.el-tabs__content) {
  flex: 1;
  min-height: 0;
}
.trash-tabs :deep(.el-tab-pane) {
  height: 100%;
  display: flex;
  flex-direction: column;
}
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
.competitor-info {
  display: flex;
  align-items: center;
  gap: 0.8vw;
}
.competitor-meta {
  display: flex;
  flex-direction: column;
  gap: 0.4vh;
  min-width: 0;
}
.competitor-name {
  font-weight: 600;
  font-size: 1.02vmax;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.competitor-domain {
  font-size: 0.8vmax;
  color: var(--app-text-color-placeholder);
}
.changes-count {
  font-size: 0.95vmax;
  color: var(--app-text-color-regular);
}
.report-icon {
  width: 48px;
  flex-shrink: 0;
}
.empty-state {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
}
.foot-note {
  flex-shrink: 0;
  font-size: 0.88vmax;
  color: var(--app-text-color-secondary);
}
</style>
