<script setup lang="ts">
import { useRoute, useRouter } from "vue-router";
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { ArrowDown } from "@element-plus/icons-vue";
import Logo from "@/components/Logo.vue";
import { ADMIN_NAV_MENUS, USER_NAV_MENUS } from "@/data/navMenu";
import { fetchMyProfile } from "@/api/user";
import { useAuthStore } from "@/stores/auth";
import { avatarColor, avatarInitials } from "@/utils/avatar";

const route = useRoute();
const router = useRouter();
const activeMenu = ref(route.name);

const auth = useAuthStore();
const user = computed(() => auth.user);
/** 侧边栏菜单：管理员进管理后台（管用户数据），普通用户看业务菜单 */
const visibleMenus = computed(() =>
  user.value?.is_admin ? ADMIN_NAV_MENUS : USER_NAV_MENUS,
);
// 头像首字母与配色用账号，保证改名称时头像不跳色
const displayName = computed(
  () => user.value?.username || user.value?.name || "",
);
/** 昵称：只用于账号区展示；与账号相同时不再重复占一行 */
const nickname = computed(() => user.value?.name || "");
const initials = computed(() => avatarInitials(displayName.value));
const avatarBg = computed(() => avatarColor(displayName.value));
const expanded = ref(false);
const footerRef = ref<HTMLElement | null>(null);

function handleClick(name: string) {
  router.push({ name });
}

/** 点击底部账号区：箭头翻转 + 展开操作面板 */
function toggleExpand(e: MouseEvent) {
  e.stopPropagation();
  expanded.value = !expanded.value;
}
function goProfile() {
  expanded.value = false;
  router.push({ name: "Setting", query: { tab: "account" } });
}
function onLogout() {
  expanded.value = false;
  auth.logout();
}

watch(
  () => route.name,
  (name) => (activeMenu.value = name),
);

// 兼容升级前已登录的会话：本地存的 user 里还没有 email 字段，补拉一次资料
//（昵称也顺带刷新）；同时挂一个点击外部关闭账号面板的监听
onMounted(async () => {
  document.addEventListener("click", onDocClick);
  const stored = auth.user as { email?: unknown } | null;
  if (!stored || typeof stored.email === "string") return;
  try {
    const profile = await fetchMyProfile();
    auth.setUser({
      id: profile.id,
      // name 存昵称；没单独设置过就用账号，保证界面始终有可展示的名字
      name: profile.nickname || profile.username,
      username: profile.username,
      avatar: profile.avatar,
      email: profile.email,
      is_admin: profile.is_admin,
    });
  } catch {
    // 拉取失败就先用占位文案，下次登录会带上
  }
});

onBeforeUnmount(() => document.removeEventListener("click", onDocClick));

function onDocClick(e: MouseEvent) {
  if (footerRef.value && !footerRef.value.contains(e.target as Node)) {
    expanded.value = false;
  }
}
</script>
<template>
  <div class="side-nav">
    <!-- logo -->
    <div class="logo" @click="$router.push({ name: 'Landing' })">
      <Logo size="1.5em" />
      <div>竞品雷达</div>
    </div>

    <!-- 菜单 -->
    <ul class="menu-list">
      <li
        class="menu-item"
        v-for="m in visibleMenus"
        :key="m.name"
        :class="{ 'menu-item--active': activeMenu === m.name }"
        @click="handleClick(m.name)"
      >
        <el-icon class="menu-icon">
          <component :is="m.icon" />
        </el-icon>
        <span class="menu-text">{{ m.label }}</span>
      </li>
    </ul>

    <!-- 底部账号区：头像 / 账号，点开箭头翻转并展开操作 -->
    <div ref="footerRef" class="footer-wrap">
      <div v-show="expanded" class="footer-panel">
        <button class="footer-action" @click="goProfile">用户中心</button>
        <button class="footer-action footer-action--danger" @click="onLogout">
          退出登录
        </button>
      </div>
      <div class="footer" @click="toggleExpand">
        <div class="footer-avatar">
          <img v-if="user?.avatar" :src="user.avatar" alt="头像" />
          <span
            v-else
            class="footer-avatar-text"
            :style="{ background: avatarBg }"
          >
            {{ initials }}
          </span>
        </div>
        <div class="footer-user">
          <!-- 昵称：账号上方展示；默认就是账号，相同时不重复占行 -->
          <span
            v-if="nickname && nickname !== user?.username"
            class="footer-nickname"
            :title="nickname"
            >{{ nickname }}</span
          >
          <span class="footer-username" :title="user?.username || '未登录'">{{
            user?.username || "未登录"
          }}</span>
          <!-- 第二行：绑定的邮箱（可用于登录、接收情报通知、找回密码）。
               未绑定时明确写「未绑定邮箱」，别回退成账号名——那会和上一行完全重复，
               而且会让人误以为账号名就是邮箱。 -->
          <span
            class="footer-account"
            :title="user?.email || '未绑定邮箱'"
          >{{ user?.email || "未绑定邮箱" }}</span>
        </div>
        <el-icon
          class="footer-expand"
          :class="{ 'footer-expand--open': expanded }"
        >
          <ArrowDown />
        </el-icon>
      </div>
    </div>
  </div>
</template>
<style scoped>
.side-nav {
  height: 100%;
  padding: 2vh 1vw;
  position: relative;
  z-index: 1;
  box-shadow: 1px 0 4px rgba(0, 0, 0, 0.06);
  display: flex;
  flex-direction: column;
}
.logo {
  display: flex;
  align-items: center;
  justify-content: center;
  /* logo 与文字之间留出间距（原来紧挨在一起） */
  gap: 0.6vw;
  font-size: 1.5vmax;
  margin-bottom: 4vh;
  cursor: pointer;
  transition: transform 0.2s ease, color 0.2s ease;
  color: var(--app-color-blue-dark-3);
}
.logo:hover{
  color: var(--app-color-blue);
  transform: scale(1.1);
}
.logo:active{
  color: var(--app-color-blue);
  transform: scale(1.05);
}
/* logo 是 PNG，不吃 color：用滤镜补上与文字同步的悬浮 / 点击反馈。
   注意：基线必须与悬浮态写同一组滤镜函数（恒等值），否则列表长度不一致时
   浏览器无法平滑插值，会先闪一帧暗色；也不要在这里用带模糊的 drop-shadow，
   过渡期间每帧重新光栅化同样会闪。 */
.logo :deep(.logo-img) {
  filter: brightness(1) saturate(1);
  will-change: filter, transform;
  transition: filter 0.2s ease, transform 0.2s ease;
}
.logo:hover :deep(.logo-img) {
  filter: brightness(1.12) saturate(1.25);
}
.logo:active :deep(.logo-img) {
  filter: brightness(0.92) saturate(1.05);
  transform: scale(0.96);
}

.menu-list {
  display: flex;
  flex-direction: column;
  gap: 1vh;
  list-style: none;
  padding: 0;
  margin: 0;
}
.menu-item {
  display: flex;
  align-items: center;
  padding: 1vh 1vw;
  margin: 0 1vw;
  gap: 1vw;
  cursor: pointer;
  transition: all 0.2s;
  font-size: 1.2vmax;
  border-radius: 1vmax;
}
.menu-item:hover {
  color: var(--app-color-purple);
  background-color: var(--app-color-purple-light-3);
}
.menu-item:active {
  color: var(--app-color-purple-light-1);
  background-color: var(--app-color-purple-light-4);
}
.menu-item--active {
  color: var(--app-color-purple);
  background-color: var(--app-color-purple-light-3);
}
.footer-wrap {
  margin-top: auto;
  position: relative;
}
.footer-panel {
  position: absolute;
  bottom: calc(100% + 0.6vh);
  left: 0;
  right: 0;
  background: #fff;
  border-radius: 0.8vmax;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.12);
  padding: 0.4vh 0.4vw;
  display: flex;
  flex-direction: column;
  gap: 0.2vh;
  z-index: 10;
}
.footer-action {
  border: none;
  background: transparent;
  text-align: left;
  padding: 0.9vh 0.8vw;
  border-radius: 0.6vmax;
  cursor: pointer;
  font-size: 0.95vmax;
  color: var(--app-text-color, #303133);
  transition: background-color 0.15s;
}
.footer-action:hover {
  background-color: var(--app-color-blue-light-5, #f0f5ff);
}
.footer-action--danger {
  color: var(--el-color-danger, #f56c6c);
}
.footer-action--danger:hover {
  background-color: var(--el-color-danger-light-9, #fef0f0);
}
.footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.6vw;
  padding: 0.6vh 0.5vw;
  border-radius: 1vmax;
  cursor: pointer;
  transition: background-color 0.2s;
}
.footer:hover {
  background-color: var(--app-color-blue-light-5);
}
.footer-avatar {
  width: 3vmax;
  height: 3vmax;
  border-radius: 50%;
  overflow: hidden;
  flex-shrink: 0;
}
.footer-avatar img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}
.footer-avatar-text {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  font-weight: 600;
  font-size: 1.4vmax;
}

.footer-user {
  display: flex;
  flex-direction: column;
  gap: 0.2vh;
  min-width: 0;
  flex: 1;
}
/* 昵称：账号上方的主展示行 */
.footer-nickname {
  font-size: 1vmax;
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.footer-username {
  font-size: 1vmax;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.footer-account {
  font-size: 0.6vmax;
  color: var(--app-text-color-regular);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.footer-expand{
  font-size: 1vmax;
  flex-shrink: 0;
  transition: transform 0.2s ease;
}
.footer-expand--open {
  transform: rotate(180deg);
}
</style>
