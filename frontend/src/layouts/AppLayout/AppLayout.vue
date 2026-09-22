<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import SideNav from "@/layouts/AppLayout/SideNav.vue";
import TopBar from "@/layouts/AppLayout/TopBar.vue";
import CompetitorFormDialog from "@/components/CompetitorFormDialog.vue";
import { useCompetitorStore } from "@/stores/competitor";
import { startSessionWatch, stopSessionWatch } from "@/composables/useSession";
import { listActiveAnnouncements, type Announcement } from "@/api/admin";

const competitorStore = useCompetitorStore();

// 多个弹窗会话（可见或后台运行）各自独立渲染；后台会话的悬浮窗按序向上堆叠
const formSessions = computed(() => competitorStore.formSessions);
const bgSessionIds = computed(() =>
  formSessions.value.filter((s) => s.background).map((s) => s.id),
);
function widgetIndexOf(id: number): number {
  return bgSessionIds.value.indexOf(id);
}

// 会话生命周期：非后台模式关闭（visible=false 且不在后台）→ 销毁会话（任务随之结束）
watch(
  () =>
    formSessions.value.map((s) => ({
      id: s.id,
      visible: s.visible,
      background: s.background,
    })),
  (snap) => {
    for (const s of snap) {
      if (!s.visible && !s.background) competitorStore.closeForm(s.id);
    }
  },
);

const CLOSED_KEY = "closed-announcements";
const announcements = ref<Announcement[]>([]);

function readClosedIds(): number[] {
  try {
    const raw = localStorage.getItem(CLOSED_KEY);
    const arr = raw ? JSON.parse(raw) : [];
    return Array.isArray(arr) ? arr.filter((n) => typeof n === "number") : [];
  } catch {
    return [];
  }
}

/** 加载当前生效公告，过滤掉已被用户关闭过的 id */
async function loadAnnouncements() {
  try {
    const all = await listActiveAnnouncements();
    const closed = new Set(readClosedIds());
    announcements.value = all.filter((a) => !closed.has(a.id));
  } catch {
    // 拉取失败静默处理：不打扰页面（后端接口错误提示不在这里重复弹）
    announcements.value = [];
  }
}

function closeAnnouncement(id: number) {
  const closed = new Set(readClosedIds());
  closed.add(id);
  localStorage.setItem(CLOSED_KEY, JSON.stringify([...closed]));
  announcements.value = announcements.value.filter((a) => a.id !== id);
}

// 会话看守只在已登录区域生效：进入 /app 启动，离开 /app（含登出跳转）停止
onMounted(() => {
  startSessionWatch();
  loadAnnouncements();
});

onUnmounted(stopSessionWatch);
</script>
<template>
  <div class="app-layout">
    <!-- 侧边栏 -->
    <aside class="aside">
      <SideNav />
    </aside>

    <!-- 主体内容区 -->
    <div class="container">
      <!-- 头部 -->
      <header class="header">
        <TopBar />
      </header>
      <!-- 平台公告横幅（内容区顶部） -->
      <div v-if="announcements.length" class="announcement-bar">
        <el-alert
          v-for="a in announcements"
          :key="a.id"
          :title="a.content"
          type="info"
          show-icon
          :closable="true"
          @close="closeAnnouncement(a.id)"
        />
      </div>
      <!-- 主体内容 -->
      <main class="main">
        <router-view />
      </main>
    </div>

    <!-- 竞品新增/编辑弹窗：挂全局层，每个会话独立实例；
         后台进行/切页后任务与右下角悬浮窗不丢，支持多个后台任务并存 -->
    <CompetitorFormDialog
      v-for="s in formSessions"
      :key="s.id"
      v-model="s.visible"
      :session-id="s.id"
      :competitor="s.competitor"
      :widget-index="widgetIndexOf(s.id)"
    />
  </div>
</template>
<style scoped>
.app-layout {
  display: flex;
  height: 100vh;
}
.aside {
  width: 15vw;
  flex-shrink: 0;
  height: 100%;
  background: linear-gradient(135deg, var(--app-color-white), var(--app-color-blue));
}
.container {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}
.header {
  height: 8vh;
  flex-shrink: 0;
  background: linear-gradient(135deg, var(--app-color-blue-light-1), var(--app-color-blue-light-3));
}
.announcement-bar {
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: 0.6vh;
  padding: 1vh 2vw 0;
}
.main {
  flex: 1;
  min-height: 0;
  background: linear-gradient(135deg, var(--app-color-white), var(--app-color-blue));
}
</style>