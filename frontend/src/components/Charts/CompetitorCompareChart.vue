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
import type { CompetitorSeries } from "@/types/trend";

use([
  CanvasRenderer,
  LineChart,
  GridComponent,
  TooltipComponent,
  LegendComponent,
  GraphicComponent,
]);

// 多竞品折线配色（色相拉开，保证每条线可区分）
const PALETTE = [
  "#4670d2",
  "#c85fd7",
  "#3cbea0",
  "#fa8c16",
  "#ff4d4f",
  "#13c2c2",
  "#8b5cf6",
  "#597ef7",
];

const COLORS = {
  textPrimary: "#303133",
  textPlaceholder: "#a8adb3",
  border: "#e5e7eb",
  empty: "#a8adb3",
};

const props = withDefaults(
  defineProps<{
    data?: CompetitorSeries[];
    height?: string;
  }>(),
  {
    data: () => [],
    height: "320px",
  },
);

const option = computed(() => buildOption(props.data ?? []));

function buildOption(list: CompetitorSeries[]) {
  const visible = list.filter((item) => item.points.length);
  if (!visible.length) {
    return {
      graphic: [
        {
          type: "text",
          left: "center",
          top: "center",
          style: { text: "暂无对比数据", fill: COLORS.empty, fontSize: 16 },
        },
      ],
      xAxis: { show: false },
      yAxis: { show: false },
      series: [],
    };
  }

  const dates = visible[0].points.map((point) => point.date);

  return {
    tooltip: {
      trigger: "axis",
      backgroundColor: "#fff",
      borderColor: COLORS.border,
      textStyle: { color: COLORS.textPrimary, fontSize: 14 },
    },
    legend: {
      top: 8,
      right: 10,
      type: "scroll",
      icon: "rect",
      itemWidth: 12,
      itemHeight: 12,
      textStyle: { color: COLORS.textPrimary, fontSize: 13 },
    },
    grid: {
      left: 20,
      right: 20,
      bottom: 20,
      top: 56,
      containLabel: true,
    },
    xAxis: {
      type: "category",
      boundaryGap: false,
      data: dates,
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: COLORS.textPlaceholder, fontSize: 13 },
    },
    yAxis: {
      type: "value",
      splitLine: { lineStyle: { type: "dashed", color: COLORS.border } },
      axisLabel: { color: COLORS.textPlaceholder, fontSize: 13 },
    },
    series: visible.map((item, index) => {
      const color = PALETTE[index % PALETTE.length];
      return {
        name: item.competitorName,
        type: "line",
        smooth: true,
        symbol: "none",
        color,
        lineStyle: { width: 2, color },
        emphasis: { lineStyle: { width: 2, color } },
        data: item.points.map((point) => point.count),
      };
    }),
  };
}
</script>
<template>
  <v-chart
    class="compare-chart"
    :style="{ height: props.height }"
    :option="option"
    autoresize
  />
</template>
<style scoped>
.compare-chart {
  width: 100%;
  display: block;
}
</style>
