<template>
  <div class="card metric-card">
    <div class="metric-label">{{ label }}</div>
    <div class="metric-value">{{ value }}</div>
    <div class="metric-sub" v-if="subtext">{{ subtext }}</div>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  label: string;
  value: string;
  subtext?: string;
}>();
</script>
