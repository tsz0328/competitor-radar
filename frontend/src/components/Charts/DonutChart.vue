<script setup lang="ts">
import { computed } from "vue";
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
      series: [],
    };
  }
  const total = list.reduce((s, d) => s + d.value, 0);
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
      itemWidth: 10,
      itemHeight: 10,
      itemGap: 10,
      textStyle: { color: COLORS.textPrimary, fontSize: FONTS.legend },
      formatter: (name: string) => {
        const item = list.find((d) => d.name === name);
        const pct = total ? (((item?.value ?? 0) / total) * 100).toFixed(1) : "0";
        return `${name}  ${pct}% (${item?.value ?? 0})`;
      },
    },
    series: [
      {
        type: "pie",
        radius: ["55%", "80%"],
        center: ["28%", "50%"],
        label: { show: false },
        emphasis: { scaleSize: 4 },
        data: list,
      },
    ],
  };
});
</script>
<template>
  <v-chart :style="{ height: props.height }" :option="option" autoresize />
</template>
