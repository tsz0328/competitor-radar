<script setup lang="ts">
import { computed } from "vue";
import VChart from "vue-echarts";
import { use } from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import { LineChart } from "echarts/charts";
import {
  GridComponent,
  TooltipComponent,
  LegendComponent,
  GraphicComponent,
} from "echarts/components";
import { graphic } from "echarts/core";
import type { ImpactTrend } from "@/types/report";

use([
  CanvasRenderer,
  LineChart,
  GridComponent,
  TooltipComponent,
  LegendComponent,
  GraphicComponent,
]);

// ===== 组件内集中管理的图表颜色 =====
const COLORS = {
  current: "#5b6fff",
  previous: "#a8adb3",
  currentGradient: ["rgba(91, 111, 255, 0.25)", "rgba(91, 111, 255, 0.02)"],
  textPrimary: "#303133",
  textSecondary: "#7a7f85",
  textPlaceholder: "#a8adb3",
  border: "#e5e7eb",
  tooltipBg: "#fff",
};
const FONTS = { legend: 13, axis: 13, tooltip: 13, empty: 14 };

const props = withDefaults(
  defineProps<{
    trend?: ImpactTrend;
    height?: string;
  }>(),
  {
    trend: () => ({ dates: [], current: [], previous: [] }),
    height: "220px",
  },
);

const option = computed(() => {
  const t = props.trend;
  if (!t?.dates.length) {
    return {
      graphic: [
        {
          type: "text",
          left: "center",
          top: "center",
          style: { text: "暂无数据", fill: COLORS.textSecondary, fontSize: FONTS.empty },
        },
      ],
      xAxis: { show: false },
      yAxis: { show: false },
      series: [],
    };
  }
  return {
    tooltip: {
      trigger: "axis",
      backgroundColor: COLORS.tooltipBg,
      borderColor: COLORS.border,
      textStyle: { color: COLORS.textPrimary, fontSize: FONTS.tooltip },
    },
    legend: {
      top: 0,
      right: 0,
      icon: "rect",
      itemWidth: 12,
      itemHeight: 4,
      data: ["本周", "上周"],
      textStyle: { color: COLORS.textPrimary, fontSize: FONTS.legend },
    },
    grid: { left: 10, right: 16, top: 34, bottom: 10, containLabel: true },
    xAxis: {
      type: "category",
      boundaryGap: false,
      data: t.dates,
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: COLORS.textPlaceholder, fontSize: FONTS.axis },
    },
    yAxis: {
      type: "value",
      minInterval: 1,
      splitLine: { lineStyle: { type: "dashed", color: COLORS.border } },
      axisLabel: { color: COLORS.textPlaceholder, fontSize: FONTS.axis },
    },
    series: [
      {
        name: "本周",
        type: "line",
        smooth: true,
        symbol: "none",
        color: COLORS.current,
        lineStyle: { width: 2, color: COLORS.current },
        areaStyle: {
          color: new graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: COLORS.currentGradient[0] },
            { offset: 1, color: COLORS.currentGradient[1] },
          ]),
        },
        data: t.current,
      },
      {
        name: "上周",
        type: "line",
        smooth: true,
        symbol: "none",
        color: COLORS.previous,
        lineStyle: { width: 2, type: "dashed", color: COLORS.previous },
        data: t.previous,
      },
    ],
  };
});
</script>
<template>
  <v-chart :style="{ height: props.height }" :option="option" autoresize />
</template>
