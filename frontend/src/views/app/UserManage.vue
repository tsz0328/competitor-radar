<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { Refresh } from "@element-plus/icons-vue";
import {
  deleteAdminUser,
  listAdminUsers,
  updateAdminUser,
  type AdminUser,
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

async function load() {
  loading.value = true;
  try {
    rows.value = await listAdminUsers(keyword.value.trim() || undefined);
  } finally {
    loading.value = false;
  }
}

function onSearch() {
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

// ---- 删除 ----
async function onDelete(row: AdminUser) {
  try {
    await ElMessageBox.confirm(
      `将删除用户「${row.username}」及其名下全部竞品、监控、情报、报告等数据，且不可恢复。确定删除吗？`,
      "删除用户",
      { type: "warning", confirmButtonText: "删除", cancelButtonText: "取消" },
    );
  } catch {
    return; // 用户取消
  }
  try {
    await deleteAdminUser(row.id);
    ElMessage.success("用户已删除");
    await load();
  } catch {
    // 错误提示由 request.ts 统一弹出
  }
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
      <el-table :data="rows" v-loading="loading" size="large">
        <el-table-column
          label="账号"
          prop="username"
          min-width="180"
          show-overflow-tooltip
        >
          <template #default="{ row }">
            <span class="username">{{ row.username }}</span>
            <el-tag v-if="row.id === selfId" size="small" type="info" effect="plain">
              当前登录
            </el-tag>
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
        <el-table-column label="操作" width="170" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openEdit(row)">修改</el-button>
            <el-button
              link
              type="danger"
              :disabled="row.id === selfId"
              @click="onDelete(row)"
            >
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <div v-if="!loading && rows.length === 0" class="empty-hint">
        没有匹配的用户
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
            active-text="管理员"
            inactive-text="普通用户"
            inline-prompt
          />
        </el-form-item>
        <el-form-item label="状态">
          <el-switch
            v-model="form.is_active"
            active-text="启用"
            inactive-text="停用"
            inline-prompt
          />
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
  </div>
</template>
<style scoped>
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

.username {
  font-weight: 600;
  margin-right: 0.5vw;
}
.muted {
  color: var(--app-color-gray);
}

.empty-hint {
  text-align: center;
  color: var(--app-color-gray);
  padding: 4vh 0;
}
</style>
