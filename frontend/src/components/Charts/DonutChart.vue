<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import VChart from "vue-echarts";
import { use } from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import { PieChart } from "echarts/charts";
import {
  TooltipComponent,
  LegendComponent,
  GraphicComponent,
} from "echarts/components";
import type { NameValue } from "@/types/report";

use([CanvasRenderer, PieChart, TooltipComponent, LegendComponent, GraphicComponent]);

// ===== 组件内集中管理的图表颜色 =====
const PALETTE = ["#5b6fff", "#fa8c16", "#22c55e", "#1890ff", "#909399"];
const COLORS = {
  textPrimary: "#303133",
  textSecondary: "#7a7f85",
  border: "#e5e7eb",
  tooltipBg: "#fff",
};
const FONTS = { legend: 13, tooltip: 13, empty: 14 };

// ===== 环图布局常量 =====
// 坑：ECharts 里 pie 的 radius 百分比基准是 min(容器宽, 容器高)/2，而 center 的百分比
// 基准是容器宽 —— 两者基准不同。卡片一窄（三列栅格里的窄卡片），半径仍是定值、
// 圆心却按比例左移，圆就左侧溢出被裁、右侧又顶进图例。所以这里放弃百分比，
// 改为量出容器实际尺寸后用像素精确定位：图例按最长文案占定宽，剩余宽度全给环图。
const CHART_EDGE = 8; // 环图距容器左/上/下的留白，同时也是与图例之间的最小间隙
const LEGEND_ICON = 10; // 图例圆点尺寸
const LEGEND_ICON_GAP = 5; // 圆点与文字之间的间距
const LEGEND_RIGHT_PAD = 6; // 图例右侧留白
const PIE_INNER_RATIO = 0.66; // 内半径 / 外半径（决定环的粗细）

const props = withDefaults(
  defineProps<{
    data?: NameValue[];
    height?: string;
  }>(),
  {
    data: () => [],
    height: "220px",
  },
);

// 容器实测尺寸：ResizeObserver 驱动，跟随窗口缩放与栅格变化
const wrapRef = ref<HTMLElement | null>(null);
const box = ref({ w: 0, h: 0 });
let resizeObserver: ResizeObserver | null = null;

onMounted(() => {
  const el = wrapRef.value;
  if (!el) return;
  const measure = () => {
    const node = wrapRef.value;
    if (!node) return;
    box.value = { w: node.clientWidth, h: node.clientHeight };
  };
  measure(); // 先同步量一次，保证首帧渲染时尺寸已就绪
  resizeObserver = new ResizeObserver(measure);
  resizeObserver.observe(el);
});

onBeforeUnmount(() => {
  resizeObserver?.disconnect();
  resizeObserver = null;
});

/** 图例文案：tooltip 与「图例占宽估算」共用同一份计算，保证两者口径一致 */
function legendLabel(name: string, list: NameValue[], total: number): string {
  const item = list.find((d) => d.name === name);
  const pct = total ? (((item?.value ?? 0) / total) * 100).toFixed(1) : "0";
  return `${name}  ${pct}% (${item?.value ?? 0})`;
}

/** 按字号估算文本像素宽：中日韩全角字符按 1em，其余按 0.56em */
function textWidth(text: string, fontSize: number): number {
  let width = 0;
  for (const ch of text) {
    width += /[\u2e80-\u9fff\uff00-\uffef]/.test(ch) ? fontSize : fontSize * 0.56;
  }
  return width;
}

const option = computed(() => {
  const list = props.data ?? [];
  if (!list.length) {
    return {
      graphic: [
        {
          type: "text",
          left: "center",
          top: "center",
          style: { text: "暂无数据", fill: COLORS.textSecondary, fontSize: FONTS.empty },
        },
      ],
      series: [],
    };
  }

  const total = list.reduce((s, d) => s + d.value, 0);
  const { w, h } = box.value;

  // 图例所需宽度 = 最宽的一项 + 圆点 + 间距 + 右侧留白
  const legendW =
    LEGEND_ICON +
    LEGEND_ICON_GAP +
    Math.ceil(
      Math.max(
        ...list.map((d) => textWidth(legendLabel(d.name, list, total), FONTS.legend)),
      ),
    ) +
    LEGEND_RIGHT_PAD;

  // 剩余宽度留给环图；容器极窄时给一个下限，保证圆还能画出来
  const plotW = Math.max(40, w - legendW);
  const cx = plotW / 2;
  // 半径同时受「可用宽度」和「容器高度」约束，取小值 → 左不裁、右不压图例
  const rOuter = Math.max(12, Math.min(cx - CHART_EDGE, h / 2 - CHART_EDGE));
  const rInner = rOuter * PIE_INNER_RATIO;

  return {
    color: PALETTE,
    tooltip: {
      trigger: "item",
      backgroundColor: COLORS.tooltipBg,
      borderColor: COLORS.border,
      textStyle: { color: COLORS.textPrimary, fontSize: FONTS.tooltip },
      formatter: (p: { name: string; value: number; percent: number }) =>
        `${p.name}：${p.value} 次（${p.percent}%）`,
    },
    legend: {
      orient: "vertical",
      right: 0,
      top: "middle",
      icon: "circle",
      itemWidth: LEGEND_ICON,
      itemHeight: LEGEND_ICON,
      itemGap: 10,
      textStyle: { color: COLORS.textPrimary, fontSize: FONTS.legend },
      formatter: (name: string) => legendLabel(name, list, total),
    },
    series: [
      {
        type: "pie",
        // 像素值（非百分比）：圆心与半径都已按容器实测尺寸算好
        center: [cx, h / 2],
        radius: [rInner, rOuter],
        label: { show: false },
        emphasis: { scaleSize: 4 },
        data: list,
      },
    ],
  };
});
</script>
<template>
  <div ref="wrapRef" class="donut-chart" :style="{ height: props.height }">
    <!-- 尺寸量到之后再渲染图表，避免首帧用 0 宽算出错误的像素布局 -->
    <v-chart v-if="box.w && box.h" class="donut-canvas" :option="option" autoresize />
  </div>
</template>

<style scoped>
.donut-chart {
  width: 100%;
}

.donut-canvas {
  width: 100%;
  height: 100%;
}
</style>
