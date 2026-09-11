<script setup lang="ts">
import { computed } from "vue";
import VChart from "vue-echarts";
import { use } from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import { BarChart } from "echarts/charts";
import {
  GridComponent,
  TooltipComponent,
  GraphicComponent,
} from "echarts/components";
import { graphic } from "echarts/core";
import type { NameValue } from "@/types/report";

use([CanvasRenderer, BarChart, GridComponent, TooltipComponent, GraphicComponent]);

// ===== 组件内集中管理的图表颜色 =====
const COLORS = {
  barStart: "#8a7bff",
  barEnd: "#5b6fff",
  textPrimary: "#303133",
  textSecondary: "#7a7f85",
  textPlaceholder: "#a8adb3",
  border: "#e5e7eb",
  tooltipBg: "#fff",
};
const FONTS = { axis: 13, tooltip: 13, empty: 14 };

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
      xAxis: { show: false },
      yAxis: { show: false },
      series: [],
    };
  }
  return {
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "none" },
      backgroundColor: COLORS.tooltipBg,
      borderColor: COLORS.border,
      textStyle: { color: COLORS.textPrimary, fontSize: FONTS.tooltip },
      formatter: (ps: { name: string; value: number }[]) =>
        `${ps[0].name}：${ps[0].value} 次变化`,
    },
    grid: { left: 8, right: 40, top: 10, bottom: 10, containLabel: true },
    xAxis: {
      type: "value",
      splitLine: { show: false },
      axisLabel: { show: false },
    },
    yAxis: {
      type: "category",
      inverse: true,
      data: list.map((d) => d.name),
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: COLORS.textPrimary, fontSize: FONTS.axis },
    },
    series: [
      {
        type: "bar",
        barWidth: 12,
        data: list.map((d) => d.value),
        label: {
          show: true,
          position: "right",
          color: COLORS.textPlaceholder,
          fontSize: FONTS.axis,
        },
        itemStyle: {
          borderRadius: [0, 6, 6, 0],
          color: new graphic.LinearGradient(0, 0, 1, 0, [
            { offset: 0, color: COLORS.barStart },
            { offset: 1, color: COLORS.barEnd },
          ]),
        },
      },
    ],
  };
});
</script>
<template>
  <v-chart :style="{ height: props.height }" :option="option" autoresize />
</template>
