<script setup lang="ts">
/**
 * 竞品图标：多级回退，保证永远不会出现"空白方块"。
 *
 * 优先用竞品自己域名的图标（一方资源，不依赖第三方服务），
 * 依次尝试后端给的地址 → favicon.ico → apple-touch-icon.png；
 * 全部失败则显示首字母头像（底色由名称哈希决定，稳定且可区分）。
 */
import { computed, onBeforeUnmount, ref, watch } from "vue";

const props = withDefaults(
  defineProps<{
    name?: string;
    domain?: string;
    /** 后端给出的首选图标地址 */
    src?: string;
    size?: number;
  }>(),
  { name: "", domain: "", src: "", size: 44 },
);

/** 从官网地址里取出主机名（去掉协议、路径、www） */
const host = computed(() =>
  (props.domain || "")
    .replace(/^https?:\/\//i, "")
    .split("/")[0]
    .replace(/^www\./i, "")
    .trim(),
);

const candidates = computed(() => {
  const list: string[] = [];
  if (props.src) list.push(props.src);
  if (host.value) {
    list.push(`https://${host.value}/favicon.ico`);
    list.push(`https://${host.value}/apple-touch-icon.png`);
  }
  return Array.from(new Set(list));
});

const index = ref(0);
const exhausted = ref(false);
const loaded = ref(false);

const currentSrc = computed(() =>
  exhausted.value ? "" : (candidates.value[index.value] ?? ""),
);

let timer: ReturnType<typeof setTimeout> | undefined;

function clearTimer() {
  if (timer) {
    clearTimeout(timer);
    timer = undefined;
  }
}

/** 换下一个候选；都试完了就标记为用尽（转为首字母头像） */
function moveNext() {
  clearTimer();
  loaded.value = false;
  if (index.value < candidates.value.length - 1) {
    index.value += 1;
  } else {
    exhausted.value = true;
  }
}

function onLoad() {
  loaded.value = true;
  clearTimer();
}

// 图片迟迟不返回也要换源，避免长时间停留在空白上
function armTimer() {
  clearTimer();
  if (currentSrc.value) timer = setTimeout(moveNext, 4000);
}

watch(
  currentSrc,
  () => {
    if (currentSrc.value) armTimer();
    else clearTimer();
  },
  { immediate: true },
);

// 目标竞品变了（例如编辑后刷新），重置回第一个候选
watch(candidates, () => {
  index.value = 0;
  exhausted.value = false;
  loaded.value = false;
});

onBeforeUnmount(clearTimer);

const initial = computed(() => {
  const source = (props.name || host.value || "?").trim();
  return source.charAt(0).toUpperCase();
});

// 固定的一组柔和配色，按名称哈希取用，保证同一竞品颜色稳定
const TONES = [
  ["#e8f1ff", "#1b5fd9"],
  ["#f0e9ff", "#6b32d9"],
  ["#fff0e6", "#c2570d"],
  ["#e6f7ee", "#12805a"],
  ["#ffe9ef", "#c81e4a"],
];

const tone = computed(() => {
  const key = props.name || host.value || "?";
  let sum = 0;
  for (let i = 0; i < key.length; i += 1) sum += key.charCodeAt(i);
  return TONES[sum % TONES.length];
});

const wrapperStyle = computed(() => ({
  width: `${props.size}px`,
  height: `${props.size}px`,
  background: loaded.value ? "var(--app-color-blue-light-5)" : tone.value[0],
  color: tone.value[1],
}));
</script>

<template>
  <div class="competitor-logo" :style="wrapperStyle">
    <span v-if="!loaded" class="logo-initial">{{ initial }}</span>
    <img
      v-if="currentSrc"
      :src="currentSrc"
      alt=""
      class="logo-img"
      @load="onLoad"
      @error="moveNext"
    />
  </div>
</template>

<style scoped>
.competitor-logo {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  overflow: hidden;
  border-radius: 0.6vmax;
  font-size: 1.1vmax;
  font-weight: 600;
  line-height: 1;
  transition: background 0.2s ease;
}
.logo-initial {
  user-select: none;
}
.logo-img {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: contain;
  display: block;
}
</style>
