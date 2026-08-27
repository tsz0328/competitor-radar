<script setup lang="ts">
import { computed } from "vue";
const props = defineProps<{ user?: { id: number; name: string; avatar: string } | null; size?: number }>();
const initials = computed(() => (props.user?.name?.trim()?.[0] ?? "?").toUpperCase());
const bg = computed(() => {
    const name = props.user?.name || "";
    let h = 0;
    for (let i = 0; i < name.length; i++) h = name.charCodeAt(i) + ((h << 5) - h);
    return `hsl(${Math.abs(h) % 360}, 60%, 55%)`;
});
const px = computed(() => props.size ?? 36);
</script>
<template>
    <img v-if="user?.avatar" :src="user.avatar"
        :style="{ width: px + 'px', height: px + 'px', borderRadius: '50%', objectFit: 'cover' }" alt="avatar" />
    <div v-else class="avatar-fallback"
        :style="{ width: px + 'px', height: px + 'px', background: bg, fontSize: px * 0.45 + 'px' }">{{ initials }}</div>
</template>
<style scoped>
.avatar-fallback {
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    color: #fff;
    font-weight: 600;
}
</style>
