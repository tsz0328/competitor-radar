<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from "vue";
import { useRouter } from "vue-router";
import {
  Bell,
  QuestionFilled,
} from "@element-plus/icons-vue";
import { useAuthStore } from "@/stores/auth";
import { useLlmStore } from "@/stores/llm";
import { useNotificationStore } from "@/stores/notification";

const router = useRouter();
const notify = useNotificationStore();
const notifyVisible = ref(false);
const auth = useAuthStore();

let unreadTimer: ReturnType<typeof setInterval> | undefined;
let es: EventSource | null = null;

/** 点开某条通知：标记已读并跳到对应事件详情（复用 P1 的 id 深链） */
function openNotification(id: number) {
  notify.markRead(id);
  notifyVisible.value = false;
  router.push({ name: "Event", query: { id: String(id) } });
}

// 顶栏展示当前 LLM 模式：真实模型 / 规则 Mock
// 状态放进 store，设置页保存成功后 refresh，徽标即时同步
const llmStore = useLlmStore();
const llmStatus = computed(() => llmStore.status);

// 未读实时刷新：优先 SSE（高优事件产生即时推红点），失败/断线回退轮询
function startPoll() {
  unreadTimer = setInterval(() => notify.refreshUnread(), 60_000);
}
function stopPoll() {
  if (unreadTimer) {
    clearInterval(unreadTimer);
    unreadTimer = undefined;
  }
}
function connectStream() {
  const token = auth.token;
  if (!token) {
    startPoll();
    return;
  }
  try {
    es = new EventSource(
      `/api/notifications/stream?token=${encodeURIComponent(token)}`,
    );
  } catch {
    startPoll();
    return;
  }
  es.onmessage = (e) => {
    try {
      const data = JSON.parse(e.data);
      if (typeof data.unread === "number") notify.setUnread(data.unread);
    } catch {
      /* 忽略畸形消息 */
    }
  };
  es.onerror = () => {
    // 断线 / 401 / 代理不支持：关闭 SSE，回退轮询
    es?.close();
    es = null;
    if (!unreadTimer) startPoll();
  };
}

onMounted(() => {
  llmStore.refresh();
  notify.load();
  connectStream();
});

onUnmounted(() => {
  if (es) es.close();
  stopPoll();
});
</script>
<template>
  <div class="top-bar">
    <div class="right">
      <el-tooltip
        v-if="llmStatus"
        :content="llmStatus.message"
        placement="bottom"
      >
        <div class="llm-badge" :class="llmStatus.mode">
          <span class="dot" />
          <span class="label">{{ llmStatus.mode === "real" ? "真实模型" : "Mock" }}</span>
        </div>
      </el-tooltip>
      <el-popover
        v-model:visible="notifyVisible"
        :width="360"
        placement="bottom-end"
        trigger="click"
        popper-class="notify-popover"
      >
        <template #reference>
          <el-badge
            :value="notify.unreadCount"
            :hidden="notify.unreadCount === 0"
            :max="99"
            class="notify-badge"
          >
            <div class="icon notify-trigger" @click="notify.load()">
              <el-icon><Bell /></el-icon>
            </div>
          </el-badge>
        </template>
        <div class="notify-panel">
          <div class="notify-head">
            <span class="notify-title">通知中心</span>
            <el-button
              link
              type="primary"
              :disabled="notify.unreadCount === 0"
              @click="notify.markAllRead()"
              >全部已读</el-button
            >
          </div>
          <div v-loading="notify.loading" class="notify-list">
            <template v-if="notify.notifications.length">
              <div
                v-for="n in notify.notifications"
                :key="n.id"
                class="notify-item"
                :class="{ unread: !notify.isRead(n.id) }"
                @click="openNotification(n.id)"
              >
                <span v-if="!notify.isRead(n.id)" class="notify-dot" />
                <div class="notify-main">
                  <div class="notify-name">{{ n.brand }}</div>
                  <div class="notify-text">{{ n.title }}</div>
                  <div class="notify-meta">
                    <span class="priority-text" :class="n.priorityType">{{
                      n.priority
                    }}</span>
                    <span>{{ n.ago }}</span>
                  </div>
                </div>
              </div>
            </template>
            <div v-else class="notify-empty">暂无高优通知</div>
          </div>
        </div>
      </el-popover>
      <div class="icon">
        <el-icon>
          <QuestionFilled />
        </el-icon>
      </div>
    </div>
  </div>
</template>
<style scoped>
.top-bar {
  height: 100%;
  padding: 0 2vw;
  display: flex;
  align-items: center;
  justify-content: flex-end;
}

.right {
  display: flex;
  align-items: center;
  gap: 2vw;
}

.icon {
  font-size: 2vmax;
}

.llm-badge {
  display: flex;
  align-items: center;
  gap: 0.4vw;
  padding: 0.4vh 0.8vw;
  border-radius: 100vmax;
  font-size: 0.85vmax;
  cursor: default;
  user-select: none;
}
.llm-badge .dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}
.llm-badge.real {
  background: var(--app-color-green-light-5);
  color: var(--app-color-green-dark-2);
}
.llm-badge.real .dot {
  background: var(--el-color-success);
}
.llm-badge.mock {
  background: var(--app-color-blue-light-5);
  color: var(--app-text-color-secondary);
}
.llm-badge.mock .dot {
  background: var(--app-text-color-placeholder);
}

/* 通知中心 */
.notify-badge {
  display: flex;
  align-items: center;
}
/* 角标叠在铃铛右上角（默认 right:10px + translateX(100%) 会被推得太远；
   外扩量越小越往图标中心靠，设为 0 则正好压住容器右上角） */
.notify-badge :deep(.el-badge__content) {
  border: none;
  top: 0;
  right: 0;
  transform: translate(12%, -12%);
}

/* 铃铛：图标居中（消除行盒导致的上偏）+ 悬浮 / 点击反馈 */
.notify-trigger {
  display: flex;
  align-items: center;
  justify-content: center;
  line-height: 1;
  width: 2.6vmax;
  height: 2.6vmax;
  border-radius: 50%;
  cursor: pointer;
  color: var(--app-text-color-regular);
  transition: background-color 0.2s ease, color 0.2s ease, transform 0.15s ease;
}
.notify-trigger:hover {
  background: color-mix(in oklch, var(--app-color-blue) 14%, transparent);
  color: var(--app-color-blue);
}
.notify-trigger:active {
  background: color-mix(in oklch, var(--app-color-blue) 22%, transparent);
  transform: scale(0.9);
}
.notify-panel {
  display: flex;
  flex-direction: column;
  max-height: 60vh;
}
.notify-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-bottom: 0.8vh;
  border-bottom: 1px solid #f0f0f0;
}
.notify-title {
  font-weight: bold;
  font-size: 1vmax;
}
.notify-list {
  margin-top: 0.6vh;
  overflow-y: auto;
  min-height: 80px;
}
.notify-item {
  display: flex;
  gap: 0.6vw;
  padding: 1vh 0.6vw;
  border-bottom: 1px solid #f5f5f5;
  cursor: pointer;
  transition: background 0.15s;
}
.notify-item:hover {
  background: #f7f9ff;
}
.notify-item.unread {
  background: #f0f7ff;
}
.notify-dot {
  width: 8px;
  height: 8px;
  margin-top: 0.6vh;
  border-radius: 50%;
  background: var(--el-color-danger);
  flex-shrink: 0;
}
.notify-main {
  min-width: 0;
  flex: 1;
}
.notify-name {
  font-size: 0.85vmax;
  color: var(--app-color-primary);
}
.notify-text {
  font-size: 0.95vmax;
  line-height: 1.5;
  margin: 0.2vh 0;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.notify-meta {
  display: flex;
  gap: 0.8vw;
  font-size: 0.8vmax;
  color: var(--app-color-gray);
}
.notify-empty {
  padding: 3vh 1vw;
  text-align: center;
  color: var(--app-color-gray);
  font-size: 0.95vmax;
}
.priority-text.high {
  color: #ff4d4f;
}
.priority-text.mid {
  color: #fa8c16;
}
.priority-text.low {
  color: #22c55e;
}
</style>
