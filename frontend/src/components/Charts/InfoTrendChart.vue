<script setup lang="ts">
/**
 * 工作台「导航型」趋势图：只表达“最近变化是变多还是变少”，
 * 点击某一天会 emit(select, dateIso)，由父组件跳到情报中心并筛选该日。
 */
import { computed, onMounted, ref } from "vue";
import VChart from "vue-echarts";
import { use } from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import { LineChart } from "echarts/charts";
import {
  GridComponent,
  TooltipComponent,
  GraphicComponent,
} from "echarts/components";
import { graphic } from "echarts/core";
import type { DailyCount } from "@/types/trend";

use([CanvasRenderer, LineChart, GridComponent, TooltipComponent, GraphicComponent]);

const LINE = "#4670d2";
const COLORS = {
  textPrimary: "#303133",
  textPlaceholder: "#a8adb3",
  border: "#e5e7eb",
  empty: "#a8adb3",
};

const props = withDefaults(
  defineProps<{ data?: DailyCount[]; height?: string }>(),
  { data: () => [], height: "260px" },
);
const emit = defineEmits<{ (e: "select", dateIso: string): void }>();

const option = computed(() => buildOption(props.data ?? []));

// 细折线本身很难点中，这里监听容器点击 + 用 echarts 暴露的像素换算定位到最近的一天，
// 这样点绘图区任意位置都能钻取，符合“点某天看当天情报”的预期。
const chartRef = ref<{
  containPixel?: (finder: unknown, point: number[]) => boolean;
  convertFromPixel?: (finder: unknown, value: number) => number;
} | null>(null);
const wrapRef = ref<HTMLElement | null>(null);

function handleClick(event: MouseEvent) {
  const chart = chartRef.value;
  const wrap = wrapRef.value;
  if (!chart?.containPixel || !chart.convertFromPixel || !wrap) return;
  const rect = wrap.getBoundingClientRect();
  const point = [event.clientX - rect.left, event.clientY - rect.top];
  if (!chart.containPixel({ gridIndex: 0 }, point)) return;
  const index = Math.round(chart.convertFromPixel({ xAxisIndex: 0 }, point[0]));
  const item = props.data?.[index];
  if (item?.dateIso) emit("select", item.dateIso);
}

onMounted(() => {
  wrapRef.value?.addEventListener("click", handleClick);
});

function buildOption(list: DailyCount[]) {
  if (!list.length) {
    return {
      graphic: [
        {
          type: "text",
          left: "center",
          top: "center",
          style: { text: "暂无趋势数据", fill: COLORS.empty, fontSize: 14 },
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
      backgroundColor: "#fff",
      borderColor: COLORS.border,
      textStyle: { color: COLORS.textPrimary, fontSize: 13 },
      formatter: (items: { axisValue: string; data: number }[]) => {
        const first = items?.[0];
        return first ? `${first.axisValue}<br/>变化 ${first.data} 条` : "";
      },
    },
    grid: { left: 12, right: 16, bottom: 8, top: 20, containLabel: true },
    xAxis: {
      type: "category",
      boundaryGap: false,
      data: list.map((d) => d.date),
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: {
        color: COLORS.textPlaceholder,
        fontSize: 12,
        interval: Math.max(0, Math.floor(list.length / 7) - 1),
      },
    },
    yAxis: {
      type: "value",
      splitLine: { lineStyle: { type: "dashed", color: COLORS.border } },
      axisLabel: { color: COLORS.textPlaceholder, fontSize: 12 },
    },
    series: [
      {
        type: "line",
        smooth: true,
        symbol: "circle",
        symbolSize: 6,
        showSymbol: false,
        lineStyle: { width: 2, color: LINE },
        itemStyle: { color: LINE },
        areaStyle: {
          color: new graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: "rgba(70, 110, 210, 0.30)" },
            { offset: 1, color: "rgba(70, 110, 210, 0.02)" },
          ]),
        },
        data: list.map((d) => d.count),
      },
    ],
  };
}
</script>
<template>
  <div ref="wrapRef" class="info-trend-wrap" :style="{ height: props.height }">
    <v-chart
      ref="chartRef"
      class="info-trend-chart"
      :option="option"
      autoresize
    />
  </div>
</template>
<style scoped>
.info-trend-wrap {
  width: 100%;
  cursor: pointer;
}

.info-trend-chart {
  width: 100%;
  height: 100%;
  display: block;
}
</style>
