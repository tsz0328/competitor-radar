<script setup lang="ts">
/**
 * 通知中心（归档视图）
 *
 * 与顶栏铃铛的区别：
 * - 铃铛=「未读收件箱」，只列近期未读、读过的消失；
 * - 这里=「全部通知」，按 days=0 拉全量高优事件（含已读），可切 全部/未读/已读。
 *
 * 已读时机沿用情报中心的安全策略：点开详情 → 抽屉主详情加载成功（emit loaded）
 * 才标已读；加载失败不标，通知仍留着、可重开重试。
 */
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import {
  fetchNotifications,
  markNotificationRead,
  markAllNotificationsRead,
} from "@/api/notification";
import { useNotificationStore } from "@/stores/notification";
import EventDetailDrawer from "@/components/EventDetailDrawer.vue";
import type { NotificationRecord } from "@/types/event";
import { Check, Bell } from "@element-plus/icons-vue";

const router = useRouter();
const notify = useNotificationStore();

const records = ref<NotificationRecord[]>([]);
const total = ref(0);
const unreadCount = ref(0);
const loading = ref(false);

type TabKey = "all" | "unread" | "read";
const tab = ref<TabKey>("all");

const counts = computed(() => ({
  all: total.value,
  unread: unreadCount.value,
  read: total.value - unreadCount.value,
}));

const filtered = computed(() => {
  if (tab.value === "unread") return records.value.filter((r) => !r.isRead);
  if (tab.value === "read") return records.value.filter((r) => r.isRead);
  return records.value;
});

// 详情抽屉状态
const detailVisible = ref(false);
const detailId = ref<number | null>(null);

async function loadArchive() {
  loading.value = true;
  try {
    const data = await fetchNotifications({ days: 0, limit: 200 });
    records.value = data.records;
    total.value = data.total;
    unreadCount.value = data.unread;
  } finally {
    loading.value = false;
  }
}

function openDetail(rec: NotificationRecord) {
  detailId.value = rec.id;
  detailVisible.value = true;
}

/** 抽屉内「相关事件」跳转：更新 id 即可，抽屉自身 watch 重新加载 */
function onSelectRelated(id: number) {
  detailId.value = id;
}

/**
 * 抽屉主详情加载成功回调：标已读（成功才标），并翻转本地 isRead、
 * 同步顶栏铃铛未读数。失败不会触发本回调，自然不标已读。
 */
async function onDetailLoaded(id: number) {
  const ack = await markNotificationRead(id);
  const rec = records.value.find((r) => r.id === id);
  if (rec) rec.isRead = true;
  notify.unreadCount = ack.unread;
}

async function markAll() {
  const ack = await markAllNotificationsRead(0);
  records.value.forEach((r) => (r.isRead = true));
  unreadCount.value = ack.unread;
  notify.unreadCount = ack.unread;
}

function goToEvent(id: number) {
  // 从通知中心点「去情报中心看」：带上 notify=1 复用情报中心的标已读深链
  detailVisible.value = false;
  router.push({ name: "Event", query: { id: String(id), notify: "1" } });
}

onMounted(loadArchive);
</script>

<template>
  <div class="notify-center-page">
    <div class="page-head card">
      <div class="head-left">
        <el-icon class="head-icon"><Bell /></el-icon>
        <div>
          <h2 class="head-title">通知中心</h2>
          <p class="head-sub">全部高优事件通知（含已读），按时间倒序</p>
        </div>
      </div>
      <el-button
        type="primary"
        :disabled="unreadCount === 0"
        @click="markAll"
        >全部已读</el-button
      >
    </div>

    <div class="tabs-bar card">
      <el-radio-group v-model="tab">
        <el-radio-button label="全部" :value="'all'" />
        <el-radio-button :label="`未读 ${counts.unread}`" :value="'unread'" />
        <el-radio-button :label="`已读 ${counts.read}`" :value="'read'" />
      </el-radio-group>
      <span class="tabs-total">共 {{ counts.all }} 条</span>
    </div>

    <div v-loading="loading" class="list-wrap card">
      <template v-if="filtered.length">
        <div
          v-for="n in filtered"
          :key="n.id"
          class="nc-item"
          :class="{ 'is-read': n.isRead }"
          @click="openDetail(n)"
        >
          <span
            class="nc-dot"
            :class="n.priorityType"
            :title="n.priority"
          />
          <span class="nc-icon" :style="{ background: n.iconBg, color: n.iconColor }">
            {{ n.iconText }}
          </span>
          <div class="nc-main">
            <div class="nc-row1">
              <span class="nc-brand">{{ n.brand }}</span>
              <el-tag
                v-if="!n.isRead"
                size="small"
                type="danger"
                effect="light"
                class="nc-unread-tag"
                >未读</el-tag
              >
              <span v-else class="nc-read-flag">
                <el-icon><Check /></el-icon>已读
              </span>
            </div>
            <div class="nc-title">{{ n.title }}</div>
            <div class="nc-meta">
              <span class="nc-source">{{ n.source || "未知页面" }}</span>
              <span class="nc-sep">·</span>
              <span>{{ n.ago }}</span>
            </div>
          </div>
          <el-button
            class="nc-go"
            link
            type="primary"
            @click.stop="goToEvent(n.id)"
            >情报中心</el-button
          >
        </div>
      </template>
      <div v-else class="nc-empty">
        {{ tab === "unread" ? "没有未读通知" : tab === "read" ? "还没有已读通知" : "暂无通知" }}
      </div>
    </div>

    <EventDetailDrawer
      v-model="detailVisible"
      :event-id="detailId"
      @select="onSelectRelated"
      @loaded="onDetailLoaded"
    />
  </div>
</template>

<style scoped>
.notify-center-page {
  padding: 1.2vmax 1.6vmax 2vmax;
  display: flex;
  flex-direction: column;
  gap: 1vmax;
}
.card {
  background: var(--app-color-white);
  border-radius: 0.6vmax;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.06);
}
.page-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1vmax 1.4vmax;
}
.head-left {
  display: flex;
  align-items: center;
  gap: 0.8vmax;
}
.head-icon {
  font-size: 1.8vmax;
  color: var(--app-color-accent, var(--app-color-purple));
}
.head-title {
  margin: 0;
  font-size: 1.3vmax;
  color: var(--app-text-color-primary);
}
.head-sub {
  margin: 0.2vmax 0 0;
  font-size: 0.85vmax;
  color: var(--app-text-color-secondary);
}
.tabs-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.7vmax 1.4vmax;
}
.tabs-total {
  font-size: 0.85vmax;
  color: var(--app-text-color-placeholder);
}
.list-wrap {
  padding: 0.4vmax 0.6vmax;
  min-height: 40vh;
}
.nc-item {
  display: flex;
  align-items: center;
  gap: 0.9vmax;
  padding: 0.9vmax 1vmax;
  border-radius: 0.5vmax;
  cursor: pointer;
  transition: background 0.15s;
}
.nc-item:hover {
  background: color-mix(in oklab, var(--app-color-blue) 8%, transparent);
}
.nc-item.is-read {
  opacity: 0.72;
}
.nc-dot {
  width: 0.7vmax;
  height: 0.7vmax;
  border-radius: 50%;
  flex-shrink: 0;
  background: var(--app-text-color-placeholder);
}
.nc-dot.high {
  background: var(--app-color-red);
}
.nc-dot.mid {
  background: var(--app-color-orange);
}
.nc-dot.low {
  background: var(--app-color-green);
}
.nc-icon {
  width: 2.6vmax;
  height: 2.6vmax;
  border-radius: 0.5vmax;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 600;
  font-size: 1.1vmax;
}
.nc-main {
  flex: 1;
  min-width: 0;
}
.nc-row1 {
  display: flex;
  align-items: center;
  gap: 0.6vmax;
}
.nc-brand {
  font-weight: 600;
  color: var(--app-text-color-primary);
  font-size: 0.95vmax;
}
.nc-unread-tag {
  transform: scale(0.85);
}
.nc-read-flag {
  display: inline-flex;
  align-items: center;
  gap: 0.2vmax;
  font-size: 0.78vmax;
  color: var(--app-text-color-placeholder);
}
.nc-title {
  margin-top: 0.2vmax;
  color: var(--app-text-color-regular);
  font-size: 0.95vmax;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.nc-meta {
  margin-top: 0.25vmax;
  font-size: 0.8vmax;
  color: var(--app-text-color-secondary);
  display: flex;
  align-items: center;
  gap: 0.4vmax;
}
.nc-sep {
  color: var(--app-text-color-placeholder);
}
.nc-go {
  flex-shrink: 0;
}
.nc-empty {
  padding: 4vmax 0;
  text-align: center;
  color: var(--app-text-color-placeholder);
  font-size: 0.95vmax;
}
</style>
