<script setup lang="ts">
import { computed } from 'vue'
import type { StatusPreset, StatusSnapshot } from '@/types/api'
const props = defineProps<{ snapshot: StatusSnapshot; presets: StatusPreset[] }>()
const current = computed(() => props.presets.find((item) => item.id === props.snapshot.status))
</script>
<template><section class="hero-card" :class="current?.color || 'awake'"><span class="eyebrow">当前状态</span><h1>{{ current?.name || `状态 ${snapshot.status}` }}</h1><p>{{ current?.desc || '服务器尚未提供状态描述' }}</p><div class="meta-row"><span>更新于 {{ new Date(snapshot.last_updated * 1000).toLocaleString() }}</span><span v-if="snapshot.private" class="badge">隐私模式</span></div></section></template>
