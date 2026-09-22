<script setup lang="ts">
import logoUrl from "@/assets/logo.svg";

defineProps({
  /** 尺寸，传 em 可跟随父级 font-size 缩放 */
  size: {
    type: String,
    default: "1.5em",
  },
});
</script>

<template>
  <img
    class="logo-img"
    :src="logoUrl"
    alt="竞品雷达"
    :style="{ width: size, height: size }"
  />
</template>

<style scoped>
.logo-img {
  display: block;
  object-fit: contain;
  flex-shrink: 0;
  user-select: none;
}
</style>
