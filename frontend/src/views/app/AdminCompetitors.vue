<script setup lang="ts">
import { onMounted, ref } from "vue";
import { ElMessage } from "element-plus";
import type { UploadRequestOptions } from "element-plus";
import { Refresh } from "@element-plus/icons-vue";
import {
  listAdminCompetitors,
  uploadCompetitorIcon,
  type AdminCompetitor,
} from "@/api/admin";
import CompetitorLogo from "@/components/CompetitorLogo.vue";

const loading = ref(false);
const rows = ref<AdminCompetitor[]>([]);
const keyword = ref("");

async function load() {
  loading.value = true;
  try {
    rows.value = await listAdminCompetitors(keyword.value.trim() || undefined);
  } finally {
    loading.value = false;
  }
}

function onSearch() {
  load();
}

// ---- 图标上传弹窗 ----
const dialogVisible = ref(false);
const uploading = ref(false);
const editing = ref<AdminCompetitor | null>(null);

function openUpload(row: AdminCompetitor) {
  editing.value = row;
  dialogVisible.value = true;
}

/** 上传前拦一道：格式白名单 + 2MB 限制（与后端口径一致），不合法就不发起请求 */
function beforeUpload(file: File) {
  const okay =
    ["image/png", "image/jpeg", "image/webp", "image/gif"].includes(file.type);
  if (!okay) {
    ElMessage.warning("仅支持 PNG / JPG / WebP / GIF 格式的图片");
    return false;
  }
  if (file.size > 2 * 1024 * 1024) {
    ElMessage.warning("图标大小不能超过 2MB");
    return false;
  }
  return true;
}

/** 覆盖 el-upload 默认上传：直接调管理员图标上传接口 */
async function doUpload(options: UploadRequestOptions) {
  if (!editing.value) return;
  uploading.value = true;
  try {
    await uploadCompetitorIcon(editing.value.id, options.file as File);
    ElMessage.success("图标已上传，同官网域名的竞品将一并更新");
    dialogVisible.value = false;
    await load();
  } catch {
    // 错误提示由 request.ts 统一弹出
  } finally {
    uploading.value = false;
  }
}

function ownerLabel(row: AdminCompetitor) {
  return row.ownerNickname || row.ownerUsername || "未知用户";
}

onMounted(load);
</script>
<template>
  <div class="admin-competitors">
    <header class="header">
      <div>
        <div class="title">全部竞品</div>
        <div class="subtitle">
          查看所有用户添加的竞品；图标缺失或不正确时，可上传官方图标（同域名竞品一并生效）
        </div>
      </div>
      <div class="actions">
        <el-button :icon="Refresh" @click="load">刷新</el-button>
      </div>
    </header>

    <section class="card filter-card">
      <el-input
        v-model="keyword"
        class="filter-item"
        placeholder="搜索竞品名称 / 官网"
        clearable
        @keyup.enter="onSearch"
        @clear="onSearch"
      />
      <el-button type="primary" @click="onSearch">搜索</el-button>
    </section>

    <section class="card table-card">
      <el-table :data="rows" v-loading="loading" size="large">
        <el-table-column label="竞品" min-width="220" show-overflow-tooltip>
          <template #default="{ row }">
            <span class="brand-cell">
              <CompetitorLogo
                :name="row.name"
                :domain="row.domain"
                :src="row.logoUrl"
                :size="32"
              />
              <span class="brand-name">{{ row.name }}</span>
            </span>
          </template>
        </el-table-column>
        <el-table-column label="归属用户" min-width="140">
          <template #default="{ row }">
            <span>{{ ownerLabel(row) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="官网" min-width="200" show-overflow-tooltip>
          <template #default="{ row }">
            <span v-if="row.domain">{{ row.domain }}</span>
            <span v-else class="muted">未填写</span>
          </template>
        </el-table-column>
        <el-table-column label="分类" prop="category" width="110" />
        <el-table-column label="状态" width="110">
          <template #default="{ row }">
            <el-tag :type="row.statusType" size="small" effect="light">
              {{ row.statusLabel }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="变化" width="110">
          <template #default="{ row }">
            <span>{{ row.changes }}</span>
            <span class="muted">（今日 +{{ row.todayChanges }}）</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="130" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openUpload(row)">
              上传图标
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <div v-if="!loading && rows.length === 0" class="empty-hint">
        没有匹配的竞品
      </div>
    </section>

    <!-- 上传图标弹窗 -->
    <el-dialog
      v-model="dialogVisible"
      :title="editing ? `上传图标：${editing.name}` : '上传图标'"
      width="420px"
    >
      <div v-if="editing" class="dialog-body">
        <div class="preview-row">
          <span class="label">当前图标</span>
          <CompetitorLogo
            :name="editing.name"
            :domain="editing.domain"
            :src="editing.logoUrl"
            :size="48"
          />
        </div>
        <el-upload
          drag
          :show-file-list="false"
          :before-upload="beforeUpload"
          :http-request="doUpload"
          accept=".png,.jpg,.jpeg,.webp,.gif"
          :disabled="uploading"
        >
          <div class="upload-hint">
            <div>点击或拖拽图片到此处</div>
            <div class="muted">PNG / JPG / WebP / GIF，不超过 2MB</div>
          </div>
        </el-upload>
      </div>
      <template #footer>
        <el-button :disabled="uploading" @click="dialogVisible = false">
          取消
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>
<style scoped>
.admin-competitors {
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

.brand-cell {
  display: inline-flex;
  align-items: center;
  gap: 0.6vw;
}
.brand-name {
  font-weight: 600;
}
.muted {
  color: var(--app-color-gray);
}

.empty-hint {
  text-align: center;
  color: var(--app-color-gray);
  padding: 4vh 0;
}

.dialog-body {
  display: flex;
  flex-direction: column;
  gap: 2vh;
}
.preview-row {
  display: flex;
  align-items: center;
  gap: 1vw;
}
.label {
  color: var(--app-color-gray);
}
.upload-hint {
  padding: 2vh 0;
  display: flex;
  flex-direction: column;
  gap: 0.4vh;
  color: var(--app-color-text, inherit);
}
.upload-hint .muted {
  font-size: 0.85vmax;
}
</style>