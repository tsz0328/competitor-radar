<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { Refresh } from "@element-plus/icons-vue";
import {
  deleteAdminUser,
  getUserOverview,
  listAdminUsers,
  updateAdminUser,
  type AdminUser,
  type UserOverview,
} from "@/api/admin";
import { useAuthStore } from "@/stores/auth";
import {
  ACCOUNT_RULE_HINT,
  isValidAccount,
  normalizeAccount,
} from "@/utils/validators";

const authStore = useAuthStore();
/** 当前登录管理员 id：不允许停用/删除自己（后端也会拦，前端置灰更直观） */
const selfId = computed(() => authStore.user?.id ?? 0);

const loading = ref(false);
const rows = ref<AdminUser[]>([]);
const keyword = ref("");
const page = ref(1);
const pageSize = ref(10);
const total = ref(0);

async function load() {
  loading.value = true;
  try {
    const res = await listAdminUsers({
      keyword: keyword.value.trim() || undefined,
      page: page.value,
      page_size: pageSize.value,
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

// ---- 修改弹窗 ----
const dialogVisible = ref(false);
const saving = ref(false);
const editingId = ref<number | null>(null);
const form = reactive({
  // 登录账号名（自定义）：改它只动后端的 username 一列；不能撞别人绑定的邮箱
  username: "",
  is_admin: false,
  is_active: true,
  new_password: "",
});
/** 打开弹窗时的原账号名：用于判断「是否真的改了」，避免保存原值时被格式规则拦住 */
const originalUsername = ref("");

/** 当前正在编辑的是否为登录者本人：是则禁用「角色 / 启用状态」两项改动 */
const editingIsSelf = computed(() => editingId.value === selfId.value);

function openEdit(row: AdminUser) {
  editingId.value = row.id;
  originalUsername.value = row.username;
  form.username = row.username;
  form.is_admin = row.is_admin;
  form.is_active = row.is_active;
  form.new_password = "";
  dialogVisible.value = true;
}

async function submitEdit() {
  const username = normalizeAccount(form.username);
  if (!username) {
    ElMessage.warning("账号不能为空");
    return;
  }
  // 只有真的改了才校验格式：存量账号名可能是邮箱形态（验证码登录自动建号时
  // 账号名就是邮箱、含 @），一律重校验会让「只改个启用状态」直接保存失败。
  // 后端也是同样的处置（见 admin.py update_user）。
  if (username !== originalUsername.value && !isValidAccount(username)) {
    ElMessage.warning(ACCOUNT_RULE_HINT);
    return;
  }
  if (!form.is_active && editingId.value === selfId.value) {
    ElMessage.warning("不能停用当前登录账号");
    return;
  }
  if (!form.is_admin && editingId.value === selfId.value) {
    ElMessage.warning("不能取消自己的管理员权限");
    return;
  }
  if (form.new_password && form.new_password.length < 6) {
    ElMessage.warning("新密码至少 6 位");
    return;
  }
  saving.value = true;
  try {
    await updateAdminUser(editingId.value as number, {
      username,
      is_admin: form.is_admin,
      is_active: form.is_active,
      new_password: form.new_password || undefined,
    });
    ElMessage.success("用户已更新");
    dialogVisible.value = false;
    await load();
  } catch {
    // 错误提示由 request.ts 统一弹出
  } finally {
    saving.value = false;
  }
}

// ---- 停用 / 启用（表格内开关） ----
async function toggleActive(row: AdminUser) {
  const next = row.is_active;
  try {
    await updateAdminUser(row.id, { is_active: next });
    ElMessage.success(next ? "已启用该账号" : "已停用该账号");
  } catch {
    // 失败回滚开关状态
    row.is_active = !next;
  }
}

// ---- 删除（需输入账号二次确认） ----
async function onDelete(row: AdminUser) {
  let input = "";
  try {
    const { value } = await ElMessageBox.prompt(
      `将删除用户「${row.username}」及其名下全部竞品、监控、情报、报告等数据，且不可恢复。`,
      "删除用户",
      {
        type: "warning",
        confirmButtonText: "删除",
        cancelButtonText: "取消",
        inputPlaceholder: `请输入账号「${row.username}」以确认`,
        inputValidator: (v: string) =>
          v === row.username ? true : `请输入正确账号「${row.username}」`,
      },
    );
    input = value;
  } catch {
    return; // 用户取消
  }
  if (input !== row.username) {
    ElMessage.warning("账号不匹配，已取消删除");
    return;
  }
  try {
    await deleteAdminUser(row.id);
    ElMessage.success("用户已删除");
    await load();
  } catch {
    // 错误提示由 request.ts 统一弹出
  }
}

// ---- 用户详情抽屉 ----
const drawerVisible = ref(false);
const overviewLoading = ref(false);
const overview = ref<UserOverview | null>(null);

async function openDetail(row: AdminUser) {
  drawerVisible.value = true;
  overviewLoading.value = true;
  overview.value = null;
  try {
    overview.value = await getUserOverview(row.id);
  } catch {
    // 错误提示由 request.ts 统一弹出
  } finally {
    overviewLoading.value = false;
  }
}

const detailTitle = computed(() =>
  overview.value ? `用户详情：${overview.value.username}` : "用户详情",
);

/** 趋势柱状图：用最大值归一化每根柱的高度（百分比） */
const trendMax = computed(() =>
  Math.max(1, ...(overview.value?.event_trend.map((d) => d.count) ?? [1])),
);
function barHeight(count: number) {
  return `${Math.max(4, Math.round((count / trendMax.value) * 100))}%`;
}

onMounted(load);
</script>
<template>
  <div class="user-manage">
    <header class="header">
      <div>
        <div class="title">用户管理</div>
        <div class="subtitle">管理平台账号：修改资料、停用/启用、删除（仅管理员可见）</div>
      </div>
      <div class="actions">
        <el-button :icon="Refresh" @click="load">刷新</el-button>
      </div>
    </header>

    <section class="card filter-card">
      <el-input
        v-model="keyword"
        class="filter-item"
        placeholder="搜索账号 / 邮箱"
        clearable
        @keyup.enter="onSearch"
        @clear="onSearch"
      />
      <el-button type="primary" @click="onSearch">搜索</el-button>
    </section>

    <section class="card table-card">
      <header class="card-head">
        <span class="card-title">用户列表</span>
        <span class="card-hint">共 {{ total }} 个账号</span>
      </header>
      <el-table :data="rows" v-loading="loading" size="large">
        <el-table-column
          label="账号"
          prop="username"
          min-width="250"
        >
          <template #default="{ row }">
            <span class="user-cell">
              <el-link type="primary" :underline="false" @click="openDetail(row)">
                <span class="username">{{ row.username }}</span>
              </el-link>
              <el-tag v-if="row.id === selfId" size="small" type="info" effect="plain">
                当前登录
              </el-tag>
            </span>
          </template>
        </el-table-column>
        <el-table-column label="邮箱" min-width="200" show-overflow-tooltip>
          <template #default="{ row }">
            <span v-if="row.email">{{ row.email }}</span>
            <span v-else class="muted">未绑定</span>
          </template>
        </el-table-column>
        <el-table-column label="角色" width="110">
          <template #default="{ row }">
            <el-tag :type="row.is_admin ? 'warning' : 'info'" size="small" effect="light">
              {{ row.is_admin ? "管理员" : "普通用户" }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="140">
          <template #default="{ row }">
            <el-switch
              v-model="row.is_active"
              :disabled="row.id === selfId"
              active-text="启用"
              inactive-text="停用"
              inline-prompt
              @change="toggleActive(row)"
            />
          </template>
        </el-table-column>
        <el-table-column label="注册时间" prop="created_at" min-width="150">
          <template #default="{ row }">
            <span v-if="row.created_at">{{ row.created_at }}</span>
            <span v-else class="muted">-</span>
          </template>
        </el-table-column>
        <el-table-column label="最近活跃" min-width="150">
          <template #default="{ row }">
            <span v-if="row.last_login_at">{{ row.last_login_at }}</span>
            <span v-else class="muted">从未登录</span>
          </template>
        </el-table-column>
        <el-table-column label="竞品" prop="competitor_count" width="90" align="right" sortable />
        <el-table-column label="情报" prop="event_count" width="90" align="right" sortable />
        <el-table-column label="周报" prop="report_count" width="90" align="right" sortable />
        <el-table-column label="抓取日志" prop="crawl_log_count" width="110" align="right" sortable />
        <el-table-column label="操作" width="190" fixed="right">
          <template #default="{ row }">
            <el-tooltip
              :disabled="row.id !== selfId"
              content="可修改账号 / 重置密码，但自己的角色与启用状态不可更改"
              placement="top"
            >
              <el-button link type="primary" @click="openEdit(row)">修改</el-button>
            </el-tooltip>
            <el-tooltip
              :disabled="row.id !== selfId"
              content="不能删除当前登录账号"
              placement="top"
            >
              <span>
                <el-button
                  link
                  type="danger"
                  :disabled="row.id === selfId"
                  @click="onDelete(row)"
                >
                  删除
                </el-button>
              </span>
            </el-tooltip>
          </template>
        </el-table-column>
      </el-table>

      <el-empty
        v-if="!loading && rows.length === 0"
        description="没有匹配的用户"
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

    <!-- 修改用户弹窗 -->
    <el-dialog v-model="dialogVisible" title="修改用户" width="460px">
      <el-form label-position="top" autocomplete="off" @submit.prevent>
        <el-form-item label="账号">
          <el-input
            v-model="form.username"
            maxlength="30"
            clearable
            placeholder="登录账号，3–30 位，字母 / 数字 / 下划线 / 中划线"
          />
        </el-form-item>
        <el-form-item label="角色">
          <el-switch
            v-model="form.is_admin"
            :disabled="editingIsSelf"
            active-text="管理员"
            inactive-text="普通用户"
            inline-prompt
          />
          <span v-if="editingIsSelf" class="field-tip">
            不能取消自己的管理员权限，请由其他管理员操作
          </span>
        </el-form-item>
        <el-form-item label="状态">
          <el-switch
            v-model="form.is_active"
            :disabled="editingIsSelf"
            active-text="启用"
            inactive-text="停用"
            inline-prompt
          />
          <span v-if="editingIsSelf" class="field-tip">
            不能停用当前登录账号
          </span>
        </el-form-item>
        <el-form-item label="重置密码">
          <el-input
            v-model="form.new_password"
            name="admin-reset-password"
            type="password"
            show-password
            autocomplete="new-password"
            maxlength="72"
            placeholder="留空表示不修改；填写则至少 6 位"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button :disabled="saving" @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submitEdit">保存</el-button>
      </template>
    </el-dialog>

    <!-- 用户详情抽屉 -->
    <el-drawer v-model="drawerVisible" :title="detailTitle" size="560px">
      <div v-loading="overviewLoading" class="drawer-body">
        <template v-if="overview">
          <section class="card detail-card">
            <header class="card-head">
              <span class="card-title">基本资料</span>
            </header>
            <div v-if="overview.is_admin || !overview.is_active" class="tag-row">
              <el-tag v-if="overview.is_admin" type="warning" size="small" effect="light">
                管理员
              </el-tag>
              <el-tag v-if="!overview.is_active" type="danger" size="small" effect="light">
                已停用
              </el-tag>
            </div>
            <div class="info-item">
              <span class="info-label">账号</span>
              <span class="info-value">{{ overview.username }}</span>
            </div>
            <div class="info-item">
              <span class="info-label">昵称</span>
              <span class="info-value">{{ overview.nickname || "未设置" }}</span>
            </div>
            <div class="info-item">
              <span class="info-label">邮箱</span>
              <span class="info-value">{{ overview.email || "未绑定" }}</span>
            </div>
            <div class="info-item">
              <span class="info-label">注册时间</span>
              <span class="info-value">{{ overview.created_at || "-" }}</span>
            </div>
            <div class="info-item">
              <span class="info-label">最近活跃</span>
              <span class="info-value">{{ overview.last_login_at || "从未登录" }}</span>
            </div>
          </section>

          <section class="card detail-card">
            <header class="card-head">
              <span class="card-title">数据统计</span>
            </header>
            <div class="stat-row">
              <div class="stat-box">
                <div class="stat-num">{{ overview.competitor_count }}</div>
                <div class="stat-name">竞品</div>
              </div>
              <div class="stat-box">
                <div class="stat-num">{{ overview.event_count }}</div>
                <div class="stat-name">情报</div>
              </div>
              <div class="stat-box">
                <div class="stat-num">{{ overview.report_count }}</div>
                <div class="stat-name">周报</div>
              </div>
              <div class="stat-box">
                <div class="stat-num">{{ overview.crawl_log_count }}</div>
                <div class="stat-name">抓取日志</div>
              </div>
            </div>
            <div class="info-item">
              <span class="info-label">抓取结果</span>
              <span class="info-value">
                成功 {{ overview.crawl_success_count }} / 失败 {{ overview.crawl_fail_count }}
              </span>
            </div>
          </section>

          <section v-if="overview.competitor_names.length" class="card detail-card">
            <header class="card-head">
              <span class="card-title">名下竞品</span>
            </header>
            <div class="tag-list">
              <el-tag
                v-for="name in overview.competitor_names"
                :key="name"
                size="small"
                effect="plain"
              >
                {{ name }}
              </el-tag>
            </div>
          </section>

          <section v-if="overview.report_titles.length" class="card detail-card">
            <header class="card-head">
              <span class="card-title">名下报告</span>
            </header>
            <ul class="text-list">
              <li v-for="title in overview.report_titles" :key="title">{{ title }}</li>
            </ul>
          </section>

          <section v-if="overview.event_trend.length" class="card detail-card">
            <header class="card-head">
              <span class="card-title">近 30 天情报趋势</span>
              <span class="card-hint">悬停查看每日条数</span>
            </header>
            <div class="trend-bars">
              <div
                v-for="d in overview.event_trend"
                :key="d.date_iso"
                class="trend-bar"
                :title="`${d.date}：${d.count} 条`"
              >
                <div class="trend-bar-fill" :style="{ height: barHeight(d.count) }" />
              </div>
            </div>
          </section>
        </template>
      </div>
    </el-drawer>
  </div>
</template>
<style scoped>
.card {
  background-color: var(--app-color-white);
  border-radius: 1vmax;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.1);
}
.user-manage {
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

.username {
  font-weight: 600;
  margin-right: 0.5vw;
}
/* 账号与「当前登录」标签同一格展示：允许换行、标签不收缩 */
.user-cell {
  display: inline-flex;
  align-items: center;
  gap: 0.5vw;
  flex-wrap: wrap;
  white-space: normal;
}
.muted {
  color: var(--app-color-gray);
}

/* 修改弹窗内「自己不可改角色/状态」的说明文字 */
.field-tip {
  display: block;
  margin-top: 0.6vh;
  font-size: 0.72vmax;
  color: var(--app-color-warning);
  line-height: 1.5;
}

.pagination {
  display: flex;
  justify-content: flex-end;
  padding-top: 0.5vh;
}

/* 抽屉 */
.drawer-body {
  display: flex;
  flex-direction: column;
  gap: 2vh;
}
.detail-card {
  padding: 1.4vh 1vw;
  display: flex;
  flex-direction: column;
  gap: 1vh;
}
.tag-row {
  display: flex;
  gap: 0.5vw;
}
.info-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 2vw;
  padding: 0.8vh 0.2vw;
  border-bottom: 1px solid var(--app-color-gray-border, #f0f0f0);
}
.info-label {
  color: var(--app-color-gray);
  font-size: 1vmax;
}
.info-value {
  font-size: 1vmax;
  word-break: break-all;
  text-align: right;
}
.stat-row {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 1vw;
}
.stat-box {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.3vh;
  padding: 1.2vh 0;
  border-radius: 0.8vmax;
  background-color: var(--app-color-blue-light-5);
}
.stat-num {
  font-size: 1.5vmax;
  font-weight: bold;
  color: var(--app-color-blue);
}
.stat-name {
  font-size: 0.85vmax;
  color: var(--app-color-gray);
}
.tag-list {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5vw;
}
.text-list {
  margin: 0;
  padding-left: 1.2vw;
  display: flex;
  flex-direction: column;
  gap: 0.4vh;
  color: var(--app-text-color-regular);
  font-size: 0.95vmax;
}
.trend-bars {
  display: flex;
  align-items: flex-end;
  gap: 2px;
  height: 120px;
}
.trend-bar {
  flex: 1;
  min-width: 0;
  height: 100%;
  display: flex;
  align-items: flex-end;
  cursor: default;
}
.trend-bar-fill {
  width: 100%;
  border-radius: 0.3vmax 0.3vmax 0 0;
  background-color: var(--app-color-blue);
  transition: opacity 0.15s;
}
.trend-bar:hover .trend-bar-fill {
  opacity: 0.75;
}
</style>