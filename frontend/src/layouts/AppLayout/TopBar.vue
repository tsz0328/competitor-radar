<script setup lang="ts">
import { computed } from "vue";
import {
  Bell,
  QuestionFilled,
  UserFilled,
  Search,
} from "@element-plus/icons-vue";
import { useAuthStore } from "@/stores/auth";
import UserAvatar from "@/components/UserAvatar.vue";

const user = computed(() => useAuthStore().user);
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
</style>
