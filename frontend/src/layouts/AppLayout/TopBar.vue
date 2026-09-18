<script setup lang="ts">
import { computed, onMounted } from "vue";
import {
  Bell,
  QuestionFilled,
  UserFilled,
  Search,
} from "@element-plus/icons-vue";
import { useAuthStore } from "@/stores/auth";
import { useLlmStore } from "@/stores/llm";
import UserAvatar from "@/components/UserAvatar.vue";

const user = computed(() => useAuthStore().user);

// 顶栏展示当前 LLM 模式：真实模型 / 规则 Mock
// 状态放进 store，设置页保存成功后 refresh，徽标即时同步
const llmStore = useLlmStore();
const llmStatus = computed(() => llmStore.status);
onMounted(() => {
  llmStore.refresh();
});
</script>
<template>
  <div class="top-bar">
    <div class="left">
      <el-input
        class="search"
        :prefix-icon="Search"
        placeholder="搜索竞品、情报、报告..."
      />
    </div>
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
      <div class="icon">
        <el-icon>
          <Bell />
        </el-icon>
      </div>
      <div class="icon">
        <el-icon>
          <QuestionFilled />
        </el-icon>
      </div>
      <UserAvatar v-if="user" :user="user" :size="40" />
      <div v-else class="avatar">
        <el-icon>
          <UserFilled />
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
  justify-content: space-between;
}

.search {
  width: 25vw;
}

.right {
  display: flex;
  align-items: center;
  gap: 2vw;
}

.icon {
  font-size: 2vmax;
}

.avatar {
  width: 3vmax;
  height: 3vmax;
  font-size: 2.5vmax;
  border-radius: 50%;
  background-color: blue;
  display: flex;
  align-items: center;
  justify-content: center;
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
</style>
