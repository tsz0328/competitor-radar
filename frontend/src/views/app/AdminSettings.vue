<script setup lang="ts">
/**
 * 系统设置（仅管理员）：SMTP 发件配置。
 * 从用户「设置」页迁出的管理端独立页面——普通用户不可见、管理员专属。
 * 语义约定：授权码明文永不回传（只回 smtp_password_set）；编辑框留空=不修改。
 */
import { computed, onMounted, reactive, ref } from "vue";
import { ElMessage } from "element-plus";
import { Bell, Message, Promotion, Refresh } from "@element-plus/icons-vue";
import {
  createAnnouncement,
  getSystemSettings,
  listAnnouncements,
  testEmail,
  updateAnnouncement,
  updateSystemSettings,
  type Announcement,
} from "@/api/admin";
import { useAuthStore } from "@/stores/auth";

const authStore = useAuthStore();

const loading = ref(false);

const sysForm = reactive({
  smtp_host: "",
  smtp_port: 465 as number | null,
  smtp_username: "",
  smtp_password: "",
  smtp_sender: "",
});
const sysPasswordSet = ref(false);
const sysEditing = ref(false);
const sysSaving = ref(false);

/** 只读展示用的授权码：已设置就显示打码，否则"未设置" */
const sysPasswordMasked = computed(() =>
  sysPasswordSet.value ? "*".repeat(12) : "未设置",
);

async function loadSystem() {
  loading.value = true;
  try {
    const s = await getSystemSettings();
    sysForm.smtp_host = s.smtp_host;
    sysForm.smtp_port = s.smtp_port || 465;
    sysForm.smtp_username = s.smtp_username;
    sysForm.smtp_sender = s.smtp_sender;
    sysPasswordSet.value = s.smtp_password_set;
    // 授权码出于安全不回传，前端始终留空（"留空=不修改"）
    sysForm.smtp_password = "";
  } catch {
    // 错误提示由 request.ts 统一弹出；表单保持上次成功加载的值
  } finally {
    loading.value = false;
  }
}

function cancelSystem() {
  sysEditing.value = false;
  sysForm.smtp_password = "";
  loadSystem();
}

async function saveSystem() {
  sysSaving.value = true;
  try {
    const s = await updateSystemSettings({
      smtp_host: sysForm.smtp_host,
      smtp_port: sysForm.smtp_port ?? 465,
      smtp_username: sysForm.smtp_username,
      smtp_sender: sysForm.smtp_sender,
      // 只有用户真填了授权码才传；空串=不改动
      smtp_password: sysForm.smtp_password,
    });
    sysForm.smtp_host = s.smtp_host;
    sysForm.smtp_port = s.smtp_port || 465;
    sysForm.smtp_username = s.smtp_username;
    sysForm.smtp_sender = s.smtp_sender;
    sysPasswordSet.value = s.smtp_password_set;
    sysForm.smtp_password = "";
    sysEditing.value = false;
    ElMessage.success("系统设置已保存");
  } catch {
    // 错误提示由 request.ts 统一弹出
  } finally {
    sysSaving.value = false;
  }
}

onMounted(() => {
  loadSystem();
  loadAnnouncements();
});

// ---- 发送测试邮件 ----
const testDialogVisible = ref(false);
const testSending = ref(false);
const testEmailTo = ref("");

function openTestEmail() {
  testEmailTo.value = authStore.user?.email ?? "";
  testDialogVisible.value = true;
}

async function sendTestEmail() {
  const to = testEmailTo.value.trim();
  if (!to) {
    ElMessage.warning("请输入收件人邮箱");
    return;
  }
  testSending.value = true;
  try {
    const res = await testEmail(to);
    if (res.ok) {
      ElMessage.success(res.message || "测试邮件已发送");
    } else {
      ElMessage.error(res.message || "测试邮件发送失败");
    }
    testDialogVisible.value = false;
  } catch {
    // 错误提示由 request.ts 统一弹出
  } finally {
    testSending.value = false;
  }
}

// ---- 平台公告 ----
const announcements = ref<Announcement[]>([]);
const annLoading = ref(false);
const annContent = ref("");
const annSaving = ref(false);

async function loadAnnouncements() {
  annLoading.value = true;
  try {
    announcements.value = await listAnnouncements();
  } catch {
    // 错误提示由 request.ts 统一弹出
  } finally {
    annLoading.value = false;
  }
}

async function publishAnnouncement() {
  const content = annContent.value.trim();
  if (!content) {
    ElMessage.warning("公告内容不能为空");
    return;
  }
  annSaving.value = true;
  try {
    await createAnnouncement(content);
    ElMessage.success("公告已发布");
    annContent.value = "";
    await loadAnnouncements();
  } catch {
    // 错误提示由 request.ts 统一弹出
  } finally {
    annSaving.value = false;
  }
}

/** 上线/下线切换：el-switch 已把新值写回 row，失败再回滚 */
async function toggleAnnouncement(row: Announcement) {
  try {
    await updateAnnouncement(row.id, { is_active: row.is_active });
    ElMessage.success(row.is_active ? "公告已上线" : "公告已下线");
  } catch {
    row.is_active = !row.is_active;
  }
}

/** ISO 时间 → 本地可读时间；解析失败原样返回 */
function formatTime(iso: string) {
  if (!iso) return "-";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}
</script>
<template>
  <div class="admin-settings">
    <header class="header">
      <div>
        <div class="title">系统设置</div>
        <div class="subtitle">SMTP 发件配置（仅管理员可改，保存后立即生效）</div>
      </div>
      <div class="actions">
        <el-button :icon="Promotion" @click="openTestEmail">发送测试邮件</el-button>
        <el-button :icon="Refresh" :loading="loading" @click="loadSystem">刷新</el-button>
      </div>
    </header>

    <section class="card panel" v-loading="loading">
      <div class="panel-head">
        <div class="panel-title-wrap">
          <span class="panel-icon"><el-icon><Message /></el-icon></span>
          <div>
            <div class="panel-title">发件配置</div>
            <div class="panel-desc">情报通知与周报推送的发件邮箱（界面配置优先于 .env）</div>
          </div>
        </div>
        <!-- 配置状态：SMTP 服务器为空 = 没在界面配置过（走 .env 回退） -->
        <el-tag :type="sysForm.smtp_host ? 'success' : 'info'" size="small" effect="light">
          {{ sysForm.smtp_host ? "已配置" : "未配置" }}
        </el-tag>
      </div>

      <!-- 只读展示：默认显示当前配置，点「修改」才变输入框 -->
      <div v-if="!sysEditing" class="account-info">
        <div class="info-item">
          <span class="info-label">SMTP 服务器</span>
          <span class="info-value">{{ sysForm.smtp_host || "未设置" }}</span>
        </div>
        <div class="info-item">
          <span class="info-label">端口</span>
          <span class="info-value">{{ sysForm.smtp_port || "未设置" }}</span>
        </div>
        <div class="info-item">
          <span class="info-label">用户名</span>
          <span class="info-value">{{ sysForm.smtp_username || "未设置" }}</span>
        </div>
        <div class="info-item">
          <span class="info-label">授权码</span>
          <span class="info-value">{{ sysPasswordMasked }}</span>
        </div>
        <div class="info-item">
          <span class="info-label">发件邮箱</span>
          <span class="info-value">{{ sysForm.smtp_sender || "未设置" }}</span>
        </div>
      </div>
      <div v-if="!sysEditing" class="actions">
        <el-button type="primary" @click="sysEditing = true">修改</el-button>
      </div>

      <!-- 编辑态：完整 SMTP 表单 -->
      <template v-if="sysEditing">
        <el-form label-position="top" autocomplete="off" @submit.prevent>
          <el-form-item label="SMTP 服务器">
            <el-input
              v-model="sysForm.smtp_host"
              maxlength="200"
              clearable
              placeholder="如 smtp.qq.com；留空则回退 .env 的 SMTP_HOST"
            />
          </el-form-item>
          <el-form-item label="端口">
            <el-input
              v-model.number="sysForm.smtp_port"
              type="number"
              placeholder="465（SSL）；587 多为 STARTTLS"
            />
          </el-form-item>
          <el-form-item label="用户名（登录账号）">
            <el-input
              v-model="sysForm.smtp_username"
              name="smtp-username"
              autocomplete="off"
              maxlength="200"
              clearable
              placeholder="通常是邮箱全名；留空则回退 .env 的 SMTP_USERNAME"
            />
          </el-form-item>
          <el-form-item label="授权码">
            <!-- new-password：明确告诉浏览器这是"新密码"字段，不要预填已保存的站点登录密码 -->
            <el-input
              v-model="sysForm.smtp_password"
              name="smtp-authcode"
              autocomplete="new-password"
              type="password"
              show-password
              maxlength="200"
              placeholder="留空表示不修改；换账号时填新账号的授权码"
            />
          </el-form-item>
          <el-form-item label="发件邮箱（SMTP From）">
            <el-input
              v-model="sysForm.smtp_sender"
              maxlength="100"
              clearable
              placeholder="如 no-reply@example.com；留空则回退 .env 的 SMTP_SENDER"
            />
          </el-form-item>
        </el-form>
        <div class="field-hint">
          服务器 / 端口 / 用户名 / 发件邮箱留空表示清掉覆盖、回退 .env；授权码留空表示不修改（出于安全不回传明文）。
          界面配置优先于 .env，保存后立即生效，无需重启。用户名与授权码必须成套，只换其一会导致登录失败、邮件发不出。
        </div>
        <div class="actions">
          <el-button type="primary" :loading="sysSaving" @click="saveSystem">
            保存
          </el-button>
          <el-button :disabled="sysSaving" @click="cancelSystem">取消</el-button>
        </div>
      </template>
    </section>

    <!-- 平台公告 -->
    <section class="card panel">
      <div class="panel-head">
        <div class="panel-title-wrap">
          <span class="panel-icon"><el-icon><Bell /></el-icon></span>
          <div>
            <div class="panel-title">平台公告</div>
            <div class="panel-desc">发布后将在所有用户登录后的页面顶部展示，可随时上线/下线</div>
          </div>
        </div>
      </div>

      <div class="announce-publish">
        <el-input
          v-model="annContent"
          type="textarea"
          :rows="2"
          maxlength="500"
          show-word-limit
          placeholder="输入公告内容，点击发布后立即上线"
        />
        <div class="actions">
          <el-button type="primary" :loading="annSaving" @click="publishAnnouncement">
            发布公告
          </el-button>
        </div>
      </div>

      <div v-loading="annLoading" class="announce-list">
        <el-empty v-if="!annLoading && announcements.length === 0" description="暂无公告" />
        <div v-for="a in announcements" :key="a.id" class="announce-item">
          <div class="announce-main">
            <div class="announce-content">{{ a.content }}</div>
            <div class="announce-time">{{ formatTime(a.created_at) }}</div>
          </div>
          <el-switch
            v-model="a.is_active"
            active-text="上线"
            inactive-text="下线"
            inline-prompt
            @change="toggleAnnouncement(a)"
          />
        </div>
      </div>
    </section>

    <!-- 发送测试邮件弹窗 -->
    <el-dialog v-model="testDialogVisible" title="发送测试邮件" width="420px">
      <el-form label-position="top" autocomplete="off" @submit.prevent>
        <el-form-item label="收件人邮箱">
          <el-input
            v-model="testEmailTo"
            name="test-email-to"
            placeholder="输入接收测试邮件的邮箱"
            clearable
            @keyup.enter="sendTestEmail"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button :disabled="testSending" @click="testDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="testSending" @click="sendTestEmail">发送</el-button>
      </template>
    </el-dialog>
  </div>
</template>
<style scoped>
.card {
  background-color: var(--app-color-white);
  border-radius: 1vmax;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.1);
}
.admin-settings {
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
  align-items: center;
  gap: 0.5vw;
}

.panel {
  padding: 2vh 1.5vw;
  display: flex;
  flex-direction: column;
  gap: 2vh;
  max-width: 880px;
}
.panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 2vw;
  flex-wrap: wrap;
}
.panel-title-wrap {
  display: flex;
  align-items: center;
  gap: 0.8vw;
}
.panel-icon {
  width: 3vmax;
  height: 3vmax;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1.4vmax;
  background-color: var(--app-color-blue-light-3);
  color: var(--app-color-blue);
}
.panel-title {
  font-size: 1.2vmax;
  font-weight: bold;
}
.panel-desc {
  font-size: 0.9vmax;
  color: var(--app-color-gray);
}

.account-info {
  display: flex;
  flex-direction: column;
  gap: 0.8vh;
}
.info-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 2vw;
  padding: 1vh 0.2vw;
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

.field-hint {
  font-size: 0.9vmax;
  color: var(--app-color-gray);
  line-height: 1.6;
  background-color: var(--app-color-blue-light-5, #f5f8ff);
  border-radius: 0.6vmax;
  padding: 1vh 1vw;
}

.announce-publish {
  display: flex;
  flex-direction: column;
  gap: 1vh;
}
.announce-list {
  display: flex;
  flex-direction: column;
  gap: 0.6vh;
}
.announce-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 2vw;
  padding: 1vh 0.2vw;
  border-bottom: 1px solid var(--app-color-gray-border, #f0f0f0);
}
.announce-main {
  min-width: 0;
  flex: 1;
}
.announce-content {
  font-size: 1vmax;
  word-break: break-all;
}
.announce-time {
  font-size: 0.85vmax;
  color: var(--app-color-gray);
  margin-top: 0.3vh;
}
</style>