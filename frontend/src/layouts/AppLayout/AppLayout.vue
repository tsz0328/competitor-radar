<script setup lang="ts">
import { onMounted, onUnmounted } from 'vue'
import SideNav from '@/layouts/AppLayout/SideNav.vue'
import TopBar from '@/layouts/AppLayout/TopBar.vue'
import { startSessionWatch, stopSessionWatch } from '@/composables/useSession'

// 会话看守只在已登录区域生效：进入 /app 启动，离开 /app（含登出跳转）停止
onMounted(startSessionWatch)
onUnmounted(stopSessionWatch)
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
      <!-- 主体内容 -->
      <main class="main">
        <router-view />
      </main>
    </div>
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
.main {
  flex: 1;
  min-height: 0;
  background: linear-gradient(135deg, var(--app-color-white), var(--app-color-blue));
}
</style>
