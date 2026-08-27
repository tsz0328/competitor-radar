<template>
    <svg viewBox="0 0 24 24" fill="none" :stroke="color || 'currentColor'" :stroke-width="strokeWidth"
        stroke-linecap="round" stroke-linejoin="round" style="width: 1em;height: 1em;display: block;"
        :style="size ? { width: size, height: size } : {}">
        <!-- 三层同心圆 + 中心圆点，匹配截图雷达靶心 -->
        <circle cx="12" cy="12" r="10" />
        <circle cx="12" cy="12" r="6.2" />
        <circle cx="12" cy="12" r="2.8" />
        <circle cx="12" cy="12" r="1.1" />
    </svg>
</template>

<script setup lang="ts">
defineProps({
    size: {
        type: String,
        default: ''
    },
    strokeWidth: {
        type: Number,
        default: 1.6
    },
    color: {
        type: String,
        default: ''
    }
})
</script>