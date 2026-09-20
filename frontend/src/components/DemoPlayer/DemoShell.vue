<script setup lang="ts">
/**
 * 演示用「假 App 外壳」
 *
 * 只复刻真实后台的框架，不下任何真实请求、不读 store。
 *
 * 结构对齐 `layouts/AppLayout/{AppLayout,SideNav,TopBar}.vue`：
 *   左侧栏（顶部 Logo + 菜单 + 底部账号区） + 右侧（顶栏 + 内容区）
 * 菜单取自 `src/data/navMenu.ts`，与真实侧边栏同一份数据源，
 * 这样演示过程中高亮项自己会走一遍产品结构，不用旁白解释。
 *
 * 尺寸按演示画布 1200×750 换算真实的比例单位：
 *   侧栏 15vw → 180px；顶栏 8vh → 60px；1vmax → 12px
 * 真实界面用的 vmax/vh/vw 在演示里换成固定 px，是因为画布固定不随视口变。
 */
import { ArrowDown, Bell, QuestionFilled } from "@element-plus/icons-vue";
import Logo from "@/components/Logo.vue";
import { NAV_MENUS } from "@/data/navMenu";

defineProps<{
  /** 当前高亮菜单，取值同真实路由 name */
  activeMenu: string;
}>();

/**
 * 演示账号（纯展示数据）：
 * 真实侧栏底部账号区取登录用户，演示里固定一个中性账号，不涉及真人信息。
 */
const account = {
  initials: "R",
  username: "radar_demo",
  email: "hello@radar.app",
};
</script>

<template>
  <div class="shell">
    <!-- 侧边栏：logo + 菜单 + 底部账号区 -->
    <aside class="shell-aside">
      <div class="shell-logo">
        <Logo size="1.5em" />
        <div class="shell-logo-text">竞品雷达</div>
      </div>

      <ul class="shell-menu">
        <li
          v-for="m in NAV_MENUS"
          :key="m.name"
          class="shell-menu-item"
          :class="{ 'shell-menu-item--on': m.name === activeMenu }"
        >
          <el-icon class="shell-menu-icon"><component :is="m.icon" /></el-icon>
          <span class="shell-menu-text">{{ m.label }}</span>
        </li>
      </ul>

      <div class="shell-account">
        <div class="shell-account-avatar">{{ account.initials }}</div>
        <div class="shell-account-info">
          <span class="shell-account-name">{{ account.username }}</span>
          <span class="shell-account-mail">{{ account.email }}</span>
        </div>
        <el-icon class="shell-account-arrow"><ArrowDown /></el-icon>
      </div>
    </aside>

    <!-- 右侧：顶栏 + 内容区 -->
    <div class="shell-container">
      <header class="shell-top">
        <div class="shell-top-right">
          <!-- 当前 LLM 模式徽标（真实 = 真实模型，否则 Mock） -->
          <span class="shell-llm">
            <i class="shell-llm-dot" />
            <span>真实模型</span>
          </span>
          <!-- 通知中心入口 -->
          <span class="shell-bell">
            <el-icon><Bell /></el-icon>
            <i class="shell-bell-count">3</i>
          </span>
          <el-icon class="shell-help"><QuestionFilled /></el-icon>
        </div>
      </header>

      <main class="shell-main">
        <slot />
      </main>
    </div>
  </div>
</template>

<style scoped>
/* ---------- 外壳 ---------- */
.shell {
  position: absolute;
  inset: 0;
  display: flex;
  font-size: 14px;
  color: var(--app-text-color-primary);
}

/* ---------- 侧边栏 ---------- */
.shell-aside {
  flex: 0 0 auto;
  width: 180px;
  padding: 15px 12px;
  display: flex;
  flex-direction: column;
  background: linear-gradient(
    135deg,
    var(--app-color-white),
    var(--app-color-blue)
  );
}

.shell-logo {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 7px;
  margin-bottom: 30px;
  font-size: 18px;
  color: var(--app-color-blue-dark-3);
}
.shell-logo-text {
  font-weight: 600;
}

.shell-menu {
  display: flex;
  flex-direction: column;
  gap: 8px;
  list-style: none;
  padding: 0;
  margin: 0;
}
.shell-menu-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 12px;
  margin: 0 2px;
  border-radius: 12px;
  font-size: 14px;
  color: var(--app-text-color-regular);
  transition: background-color 0.35s ease, color 0.35s ease;
}
.shell-menu-icon {
  font-size: 16px;
}
.shell-menu-text {
  white-space: nowrap;
}
.shell-menu-item--on {
  font-weight: 600;
  color: var(--app-color-purple);
  background: var(--app-color-purple-light-3);
}

/* 底部账号区 */
.shell-account {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: auto;
  padding: 6px;
  border-radius: 12px;
}
.shell-account-avatar {
  flex: 0 0 auto;
  width: 36px;
  height: 36px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 15px;
  font-weight: 600;
  color: var(--app-color-white);
  background: var(--app-color-accent);
}
.shell-account-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.shell-account-name {
  font-size: 12px;
  color: var(--app-text-color-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.shell-account-mail {
  /* 真实是 0.6vmax（1200 画布下约 7px），演示里抬到 10px 保证缩放后仍可辨 */
  font-size: 10px;
  color: var(--app-text-color-regular);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.shell-account-arrow {
  flex: 0 0 auto;
  font-size: 12px;
  color: var(--app-text-color-secondary);
}

/* ---------- 右侧 ---------- */
.shell-container {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}

/* 顶栏：真实只有右侧三个元素（LLM 徽标 / 通知铃铛 / 帮助），不做检索 */
.shell-top {
  flex: 0 0 auto;
  height: 60px;
  display: flex;
  align-items: center;
  padding: 0 24px;
  background: linear-gradient(
    135deg,
    var(--app-color-blue-light-1),
    var(--app-color-blue-light-3)
  );
}
.shell-top-right {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 20px;
  color: var(--app-text-color-regular);
}
.shell-llm {
  display: flex;
  align-items: center;
  gap: 6px;
  height: 26px;
  padding: 0 11px;
  border-radius: 13px;
  font-size: 12px;
  background: color-mix(in oklab, var(--app-color-white) 72%, transparent);
}
.shell-llm-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--app-color-green);
}
.shell-bell {
  position: relative;
  display: flex;
  align-items: center;
  font-size: 17px;
}
.shell-bell-count {
  position: absolute;
  top: -7px;
  right: -10px;
  min-width: 15px;
  height: 15px;
  padding: 0 4px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 10px;
  font-style: normal;
  line-height: 1;
  color: var(--app-color-white);
  background: var(--app-color-red);
}
.shell-help {
  font-size: 17px;
}

.shell-main {
  position: relative;
  flex: 1;
  min-height: 0;
  padding: 20px 22px;
  display: flex;
  flex-direction: column;
  gap: 16px;
  background: linear-gradient(
    135deg,
    var(--app-color-white),
    var(--app-color-blue)
  );
}
</style>
