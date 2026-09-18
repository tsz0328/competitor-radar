<script setup lang="ts">
/**
 * 竞品图标：多级回退，保证永远不会出现"空白方块"。
 *
 * 优先用竞品自己域名的图标（一方资源，不依赖第三方服务）：
 *   1) 后端给的地址 → favicon.ico → apple-touch-icon.png；
 *   2) 全失败时兜底调用后端解析首页 <link rel="icon"> 拿真实图标
 *      —— SPA 站点（如豆包）会把 /favicon.ico 返回成 HTML，真实图标在 CDN 上；
 *   3) 仍拿不到才显示首字母头像（底色由名称哈希决定，稳定且可区分）。
 */
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { resolveFavicon } from "@/api/competitor";

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

/** 本地可直接拼出的候选：后端给的地址 → favicon.ico → apple-touch-icon.png */
const baseCandidates = computed(() => {
  const list: string[] = [];
  if (props.src) list.push(props.src);
  if (host.value) {
    list.push(`https://${host.value}/favicon.ico`);
    list.push(`https://${host.value}/apple-touch-icon.png`);
  }
  return Array.from(new Set(list));
});

// 本地候选全失败后，由后端解析出的"真实图标"（SPA 站点图标常挂在 CDN 上）
const remoteSrc = ref("");
const remoteTried = ref(false);

const candidates = computed(() =>
  remoteSrc.value ? [...baseCandidates.value, remoteSrc.value] : baseCandidates.value,
);

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

/** 换下一个候选；本地候选都试完了就去后端解析真实图标，最后才转首字母头像 */
async function moveNext() {
  clearTimer();
  loaded.value = false;
  if (index.value < candidates.value.length - 1) {
    index.value += 1;
    return;
  }

  // 本地候选全失败：兜底问后端要真实图标（每个组件实例只问一次）
  if (!remoteTried.value && host.value) {
    remoteTried.value = true;
    try {
      const { logoUrl } = await resolveFavicon(host.value);
      if (logoUrl && !candidates.value.includes(logoUrl)) {
        remoteSrc.value = logoUrl;
        index.value = candidates.value.length - 1; // 指向刚追加的远程候选
        return; // currentSrc 变化会触发 watch，重新计时加载
      }
    } catch {
      // 解析失败无所谓，继续走首字母头像
    }
  }
  exhausted.value = true;
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

// 目标竞品变了（例如编辑后刷新），重置回第一个候选（含清掉远程解析结果）
watch(baseCandidates, () => {
  index.value = 0;
  exhausted.value = false;
  loaded.value = false;
  remoteSrc.value = "";
  remoteTried.value = false;
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
    <!--
      仅用于"指称"竞品身份的内部展示，不构成任何关联/背书暗示。
      referrerpolicy=no-referrer：避免把本页面路径泄露给竞品站，
      也降低因对方防盗链（Referer 校验）而加载失败的概率。
      图片仅为缓存给内部使用，不做对外分发。
    -->
    <img
      v-if="currentSrc"
      :src="currentSrc"
      alt=""
      class="logo-img"
      referrerpolicy="no-referrer"
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
