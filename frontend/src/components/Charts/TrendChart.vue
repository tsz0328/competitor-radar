<script setup lang="ts">
import { computed } from 'vue'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { LineChart } from 'echarts/charts'
import {
    GridComponent,
    TooltipComponent,
    LegendComponent,
    GraphicComponent
} from 'echarts/components'
import { graphic } from 'echarts/core'
import type { TrendPoint } from '@/types/trend'

use([
    CanvasRenderer,
    LineChart,
    GridComponent,
    TooltipComponent,
    LegendComponent,
    GraphicComponent
]);

// ===== 组件内集中管理的图表颜色（对应全局 OKLCH 色板，统一用 hex 保证 canvas 稳定渲染） =====
const COLORS = {
    // 折线主色（色相拉开，增强区分度）
    feature: "#4670d2",      // 功能更新 → 蓝
    price: "#c85fd7",        // 价格变动 → 紫(偏品红)
    sentiment: "#3cbea0",    // 舆论热度 → 绿
    // 渐变（RGBA，带透明度）
    featureGradient: ["rgba(70, 110, 210, 0.3)", "rgba(70, 110, 210, 0.02)"],
    priceGradient: ["rgba(200, 95, 215, 0.25)", "rgba(200, 95, 215, 0.02)"],
    sentimentGradient: ["rgba(60, 190, 160, 0.25)", "rgba(60, 190, 160, 0.02)"],
    // 文字 / 边框 / 分割线
    textPrimary: "#303133",
    textSecondary: "#7a7f85",
    textPlaceholder: "#a8adb3",
    border: "#e5e7eb",
    tooltipBg: "#fff",
};

// ===== 组件内统一管理的图表字号（ECharts 默认 12px，可自行调整） =====
const FONTS = {
    legend: 16,      // 图例文字
    axis: 16,        // 横/纵坐标轴刻度
    tooltip: 16,     // 悬停提示文字
    empty: 16,       // 空数据提示文字
};

const props = withDefaults(
    defineProps<{
        data?: TrendPoint[];
        height?: string;
    }>(),
    {
        data: () => [],
        height: "300px",
    },
);

const option = computed(() => buildOption(props.data ?? []))

function buildOption(list: TrendPoint[]) {
    // 空数据兜底
    if (!list.length) {
        return {
            graphic: [{
                type: 'text',
                left: 'center',
                top: 'center',
                style: { text: '暂无趋势数据', fill: COLORS.textSecondary, fontSize: FONTS.empty }
            }],
            xAxis: { show: false },
            yAxis: { show: false },
            series: []
        }
    }

    return {
        tooltip: {
            trigger: "axis",
            backgroundColor: COLORS.tooltipBg,
            borderColor: COLORS.border,
            textStyle: { color: COLORS.textPrimary, fontSize: FONTS.tooltip },
        },
        legend: {
            top: 10,
            right: 10,
            icon: "rect",
            itemWidth: 12,
            itemHeight: 12,
            data: ["功能更新", "价格变动", "舆论热度"],
            textStyle: { color: COLORS.textPrimary, fontSize: FONTS.legend },
        },
        grid: {
            left: 20,
            right: 20,
            bottom: 20,
            top: 60,
            containLabel: true,
        },
        xAxis: {
            type: "category",
            boundaryGap: false,
            data: list.map((d) => d.date),
            axisLine: { show: false },
            axisTick: { show: false },
            axisLabel: { color: COLORS.textPlaceholder, fontSize: FONTS.axis },
        },
        yAxis: {
            type: "value",
            splitLine: { lineStyle: { type: "dashed", color: COLORS.border } },
            axisLabel: { color: COLORS.textPlaceholder, fontSize: FONTS.axis },
        },
        series: [
            {
                name: "功能更新",
                type: "line",
                smooth: true,
                symbol: "none",
                color: COLORS.feature,
                lineStyle: { width: 2, color: COLORS.feature },
                emphasis: { lineStyle: { width: 2, color: COLORS.feature } },
                areaStyle: {
                    color: new graphic.LinearGradient(0, 0, 0, 1, [
                        { offset: 0, color: COLORS.featureGradient[0] },
                        { offset: 1, color: COLORS.featureGradient[1] },
                    ]),
                },
                data: list.map(d => d.feature),
            },
            {
                name: "价格变动",
                type: "line",
                smooth: true,
                symbol: "none",
                color: COLORS.price,
                lineStyle: { width: 2, color: COLORS.price },
                emphasis: { lineStyle: { width: 2, color: COLORS.price } },
                areaStyle: {
                    color: new graphic.LinearGradient(0, 0, 0, 1, [
                        { offset: 0, color: COLORS.priceGradient[0] },
                        { offset: 1, color: COLORS.priceGradient[1] },
                    ]),
                },
                data: list.map(d => d.price),
            },
            {
                name: "舆论热度",
                type: "line",
                smooth: true,
                symbol: "none",
                color: COLORS.sentiment,
                lineStyle: { width: 2, color: COLORS.sentiment },
                emphasis: { lineStyle: { width: 2, color: COLORS.sentiment } },
                areaStyle: {
                    color: new graphic.LinearGradient(0, 0, 0, 1, [
                        { offset: 0, color: COLORS.sentimentGradient[0] },
                        { offset: 1, color: COLORS.sentimentGradient[1] },
                    ]),
                },
                data: list.map(d => d.sentiment),
            },
        ],
    }
}
</script>
<template>
  <v-chart class="trend-chart" :style="{ height: props.height }" :option="option" autoresize />
</template>
<style scoped>
.trend-chart {
  width: 100%;
  display: block;
}
</style>