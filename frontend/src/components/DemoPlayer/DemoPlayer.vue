<script setup lang="ts">
/**
 * 落地页「产品演示」播放器
 *
 * 组成：
 *   DemoShell（假 App 外壳）+ 四幕场景组件 + 焦点遮罩 + 假光标 + HUD
 *
 * 三个关键取舍：
 * 1. 固定 1200×750 设计画布，再用 transform: scale() 适配容器宽度 —— 幕内所有
 *    坐标都能按 1:1 手摆，不用一堆 cqw/em 换算。
 * 2. 焦点遮罩用「同一份界面渲染两层」实现：底层整体模糊降饱和，上层用
 *    clip-path: inset(... round ...) 抠出清晰的焦点窗口。比 mask-composite 挖洞
 *    更稳，而且圆角是真圆角，不会被方形洞口穿帮。
 * 3. 进度条直接写 DOM style，不走响应式 —— 否则每帧都会重渲染整个舞台子树。
 */
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import type { ComponentPublicInstance } from "vue";
import { RefreshRight, VideoPlay, VideoPause } from "@element-plus/icons-vue";

import DemoShell from "./DemoShell.vue";
import SceneCompetitor from "./scenes/SceneCompetitor.vue";
import SceneEvent from "./scenes/SceneEvent.vue";
import SceneReport from "./scenes/SceneReport.vue";
import SceneTrend from "./scenes/SceneTrend.vue";
import {
  DESIGN_H,
  DESIGN_W,
  SCENES,
  SCENE_GAP_MS,
  TOTAL_MS,
  type DemoFocus,
} from "./script";

const props = withDefaults(
  defineProps<{
    /** 打开时从第几幕开始播（越界自动夹到合法范围），默认第 1 幕 */
    initialScene?: number;
  }>(),
  { initialScene: 0 },
);

/** 场景组件顺序与 SCENES 一一对应 */
const sceneComps = [SceneCompetitor, SceneEvent, SceneReport, SceneTrend];

/** 每幕的起始时间点，供点击跳转 */
const sceneStarts = SCENES.map((_, i) =>
  SCENES.slice(0, i).reduce(
    (sum, sc) => sum + sc.stepMs * sc.steps.length + SCENE_GAP_MS,
    0,
  ),
);

/** 焦点窗口圆角（设计画布坐标） */
const FOCUS_RADIUS = 18;

const stageRef = ref<HTMLElement | null>(null);
const scale = ref(1);
const sceneIndex = ref(0);
const stepIdx = ref(0);
const playing = ref(true);

/** 非响应式的播放进度，避免每帧触发重渲染 */
let elapsedMs = 0;
let rafId = 0;
let lastTs = 0;
const segEls: (HTMLElement | null)[] = [];

const currentScene = computed(() => SCENES[sceneIndex.value]);
const currentComp = computed(() => sceneComps[sceneIndex.value]);

/** 取当前步（含之前最近的声明）生效的焦点窗口 */
const focus = computed<DemoFocus>(() => {
  const sc = SCENES[sceneIndex.value];
  for (let i = stepIdx.value; i >= 0; i--) {
    const f = sc.steps[i]?.focus;
    if (f) return f;
  }
  return sc.focus;
});

/** 取当前步（含之前最近的声明）生效的光标位置 */
const cursorPos = computed(() => {
  const sc = SCENES[sceneIndex.value];
  for (let i = stepIdx.value; i >= 0; i--) {
    const c = sc.steps[i]?.cursor;
    if (c) return c;
  }
  return { x: DESIGN_W / 2, y: DESIGN_H / 2 };
});

/** 焦点窗口在画布内的 clip-path，用于抠出清晰层 */
const crispClip = computed(() => {
  const f = focus.value;
  return `inset(${f.y}px ${DESIGN_W - f.x - f.w}px ${
    DESIGN_H - f.y - f.h
  }px ${f.x}px round ${FOCUS_RADIUS}px)`;
});

const focusBoxStyle = computed(() => ({
  width: `${focus.value.w}px`,
  height: `${focus.value.h}px`,
  transform: `translate(${focus.value.x}px, ${focus.value.y}px)`,
}));

const cursorStyle = computed(() => ({
  transform: `translate(${cursorPos.value.x}px, ${cursorPos.value.y}px)`,
}));

/** 根据播放进度刷新幕 / 步 / 进度条 */
function apply(t: number) {
  let rest = t;
  let index = SCENES.length - 1;
  let step = 0;

  for (let i = 0; i < SCENES.length; i++) {
    const sc = SCENES[i];
    const dur = sc.stepMs * sc.steps.length;
    if (rest < dur) {
      index = i;
      step = Math.min(sc.steps.length - 1, Math.floor(rest / sc.stepMs));
      break;
    }
    rest -= dur;
    index = i;
    step = sc.steps.length - 1;
    if (rest < SCENE_GAP_MS) break;
    rest -= SCENE_GAP_MS;
  }

  if (sceneIndex.value !== index) sceneIndex.value = index;
  if (stepIdx.value !== step) stepIdx.value = step;
  paintSegments(t);
}

/** 进度条：直接改 transform，不参与响应式 */
function paintSegments(t: number) {
  let rest = t;
  for (let i = 0; i < SCENES.length; i++) {
    const sc = SCENES[i];
    const dur = sc.stepMs * sc.steps.length;
    const p = Math.max(0, Math.min(1, rest / dur));
    const fill = segEls[i]?.querySelector<HTMLElement>(".seg-fill");
    if (fill) fill.style.transform = `scaleX(${p})`;
    rest -= dur + SCENE_GAP_MS;
  }
}

function loop(ts: number) {
  if (!lastTs) lastTs = ts;
  const dt = ts - lastTs;
  lastTs = ts;
  if (playing.value) {
    elapsedMs = (elapsedMs + dt) % TOTAL_MS;
    apply(elapsedMs);
  }
  rafId = requestAnimationFrame(loop);
}

function toggle() {
  playing.value = !playing.value;
  lastTs = 0;
}

function restart() {
  elapsedMs = 0;
  apply(0);
  playing.value = true;
  lastTs = 0;
}

function seek(i: number) {
  elapsedMs = sceneStarts[i];
  apply(elapsedMs);
  playing.value = true;
  lastTs = 0;
}

function setSegRef(i: number, el: Element | ComponentPublicInstance | null) {
  segEls[i] = (el as HTMLElement) ?? null;
}

let ro: ResizeObserver | null = null;
let io: IntersectionObserver | null = null;

onMounted(() => {
  const stage = stageRef.value;
  if (!stage) return;

  const fit = () => {
    const w = stage.clientWidth;
    // 容器展开动画期间宽度可能还是 0，跳过这一帧等 ResizeObserver 再报一次
    if (w > 0) scale.value = w / DESIGN_W;
  };
  fit();
  ro = new ResizeObserver(fit);
  ro.observe(stage);

  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  // 从指定幕开始（越界夹到合法范围）
  const startIdx = Math.min(Math.max(props.initialScene, 0), SCENES.length - 1);
  elapsedMs = sceneStarts[startIdx];
  apply(elapsedMs);

  // 尊重系统的「减弱动态效果」偏好：不自动播放，交给用户点播放
  if (reduced) playing.value = false;

  // 首次滚入视口才从头播：落地页里访客未必马上滚到这一屏，
  // 若页面一加载就开播，等看到时开头已经过去了。
  if (!reduced) {
    io = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (!entry.isIntersecting) return;
          elapsedMs = sceneStarts[startIdx];
          apply(elapsedMs);
          lastTs = 0;
          io?.disconnect();
          io = null;
        });
      },
      { threshold: 0.25 },
    );
    io.observe(stage);
  }

  rafId = requestAnimationFrame(loop);
});

onBeforeUnmount(() => {
  cancelAnimationFrame(rafId);
  ro?.disconnect();
  io?.disconnect();
});
</script>

<template>
  <div class="player">
    <div ref="stageRef" class="stage">
      <div class="canvas" :style="{ transform: `scale(${scale})` }">
        <!-- 底层：非焦点区（降饱和 + 变淡） -->
        <div class="layer layer--dim">
          <DemoShell :key="currentScene.id" :active-menu="currentScene.menu">
            <component :is="currentComp" :step="stepIdx" />
          </DemoShell>
        </div>

        <!-- 上层：只保留焦点窗口内那部分清晰 -->
        <div class="layer layer--crisp" :style="{ clipPath: crispClip }">
          <DemoShell :active-menu="currentScene.menu">
            <component :is="currentComp" :step="stepIdx" />
          </DemoShell>
        </div>

        <!-- 焦点窗口描边 -->
        <div class="ring" :style="focusBoxStyle" />

        <!-- 假光标 -->
        <div class="cursor" :style="cursorStyle">
          <i class="cursor-dot" />
        </div>
      </div>

      <!-- 暂停时的遮罩与播放按钮 -->
      <button v-if="!playing" class="play-mask" type="button" @click="toggle">
        <el-icon class="play-mask-icon"><VideoPlay /></el-icon>
        <span>继续演示</span>
      </button>
    </div>

    <div class="hud">
      <div class="hud-btns">
        <button class="hud-btn" type="button" @click="toggle">
          <el-icon>
            <VideoPause v-if="playing" />
            <VideoPlay v-else />
          </el-icon>
        </button>
        <button class="hud-btn" type="button" @click="restart">
          <el-icon><RefreshRight /></el-icon>
        </button>
      </div>

      <div class="segs">
        <button
          v-for="(sc, i) in SCENES"
          :key="sc.id"
          :ref="(el) => setSegRef(i, el)"
          class="seg"
          :class="{ 'seg--on': i === sceneIndex }"
          type="button"
          @click="seek(i)"
        >
          <span class="seg-bar"><i class="seg-fill" /></span>
          <span class="seg-name">{{ sc.menuLabel }}</span>
          <span class="seg-cap">{{ sc.caption }}</span>
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.player {
  display: flex;
  flex-direction: column;
  gap: 14px;
  width: 100%;
  margin: 0 auto;
}

/* ---------- 舞台 ---------- */
.stage {
  position: relative;
  width: 100%;
  aspect-ratio: 1200 / 750;
  border-radius: 18px;
  overflow: hidden;
  background: var(--app-color-white);
  border: 2px solid color-mix(in oklab, var(--app-color-blue) 18%, transparent);
}
.canvas {
  position: absolute;
  left: 0;
  top: 0;
  width: 1200px;
  height: 750px;
  transform-origin: top left;
}
.layer {
  position: absolute;
  inset: 0;
}
.layer--dim {
  /* 不做模糊（2026-09-20 用户选择）：背景保持完全可读，
     只靠降饱和 + 轻微变淡把它压成"非重点"，焦点窗则由彩色 + 描边跳出 */
  filter: saturate(0.55);
  opacity: 0.9;
}
.layer--crisp {
  transition: clip-path 0.9s cubic-bezier(0.22, 1, 0.36, 1);
}
.ring {
  position: absolute;
  left: 0;
  top: 0;
  border-radius: 18px;
  border: 2.5px solid var(--app-color-blue);
  box-shadow: 0 0 0 6px color-mix(in oklab, var(--app-color-blue) 14%, transparent);
  pointer-events: none;
  transition: transform 0.9s cubic-bezier(0.22, 1, 0.36, 1),
    width 0.9s cubic-bezier(0.22, 1, 0.36, 1),
    height 0.9s cubic-bezier(0.22, 1, 0.36, 1);
}
.cursor {
  position: absolute;
  left: 0;
  top: 0;
  pointer-events: none;
  transition: transform 0.9s cubic-bezier(0.22, 1, 0.36, 1);
}
.cursor-dot {
  display: block;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  transform: translate(-50%, -50%);
  background: var(--app-color-black);
  border: 3px solid var(--app-color-white);
  box-shadow: 0 2px 10px color-mix(in oklab, var(--app-color-black) 45%, transparent);
}

.play-mask {
  position: absolute;
  inset: 0;
  width: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  border: none;
  cursor: pointer;
  font-size: 15px;
  font-weight: 600;
  color: var(--app-color-white);
  background: color-mix(in oklab, var(--app-color-black) 46%, transparent);
}
.play-mask-icon {
  font-size: 44px;
}

/* ---------- HUD ---------- */
.hud {
  display: flex;
  align-items: stretch;
  gap: 12px;
}
.hud-btns {
  flex: 0 0 auto;
  display: flex;
  gap: 8px;
}
.hud-btn {
  width: 40px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  font-size: 17px;
  color: var(--app-color-blue);
  background: color-mix(in oklab, var(--app-color-blue) 9%, transparent);
  border: 2px solid color-mix(in oklab, var(--app-color-blue) 20%, transparent);
  transition: background-color 0.2s ease;
}
.hud-btn:hover {
  background: color-mix(in oklab, var(--app-color-blue) 16%, transparent);
}
.segs {
  flex: 1;
  min-width: 0;
  display: flex;
  gap: 10px;
}
.seg {
  flex: 1;
  min-width: 0;
  padding: 9px 11px;
  border-radius: 12px;
  display: flex;
  flex-direction: column;
  gap: 7px;
  text-align: left;
  cursor: pointer;
  background: color-mix(in oklab, var(--app-color-blue) 5%, transparent);
  border: 2px solid transparent;
  transition: background-color 0.3s ease, border-color 0.3s ease;
}
.seg--on {
  background: color-mix(in oklab, var(--app-color-blue) 11%, transparent);
  border-color: color-mix(in oklab, var(--app-color-blue) 30%, transparent);
}
.seg-bar {
  display: block;
  height: 4px;
  border-radius: 3px;
  overflow: hidden;
  background: color-mix(in oklab, var(--app-color-blue) 16%, transparent);
}
.seg-fill {
  display: block;
  height: 100%;
  border-radius: 3px;
  background: var(--app-color-blue);
  transform: scaleX(0);
  transform-origin: left center;
}
.seg-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--app-text-color-primary);
}
.seg-cap {
  font-size: 11.5px;
  line-height: 1.4;
  color: var(--app-text-color-secondary);
}
</style>
