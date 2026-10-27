<template>
  <div :class="['metric-card', variantClass]">
    <div class="metric-top">
      <span class="metric-label">{{ label }}</span>
      <span class="metric-icon" v-if="icon">{{ icon }}</span>
    </div>
    <div class="metric-value">{{ value }}</div>
    <div class="metric-sub" v-if="subtext">
      <span class="metric-sub-text">{{ subtext }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";

const props = defineProps<{
  label: string;
  value: string;
  subtext?: string;
  icon?: string;
  variant?: "primary" | "emerald" | "purple" | "amber" | "default";
}>();

const variantClass = computed(() => `variant-${props.variant || "default"}`);
</script>

<style scoped>
.metric-card {
  position: relative;
  background: linear-gradient(135deg, rgba(255, 255, 255, 0.04) 0%, rgba(255, 255, 255, 0.01) 100%), var(--bg-surface, #0f1523);
  border: 1px solid var(--border-color, rgba(255, 255, 255, 0.08));
  border-radius: 16px;
  padding: 20px 22px;
  box-shadow: 0 4px 20px -2px rgba(0, 0, 0, 0.35), inset 0 1px 0 rgba(255, 255, 255, 0.06);
  transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  overflow: hidden;
}

.metric-card::before {
  content: "";
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 2px;
  background: linear-gradient(90deg, transparent, rgba(56, 189, 248, 0.6), transparent);
  opacity: 0;
  transition: opacity 0.3s ease;
}

.metric-card:hover {
  transform: translateY(-3px);
  border-color: rgba(56, 189, 248, 0.3);
  box-shadow: 0 12px 30px -4px rgba(0, 0, 0, 0.5), 0 0 20px rgba(56, 189, 248, 0.15), inset 0 1px 0 rgba(255, 255, 255, 0.12);
}

.metric-card:hover::before {
  opacity: 1;
}

.metric-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.metric-label {
  font-size: 11.5px;
  font-weight: 700;
  letter-spacing: 0.8px;
  text-transform: uppercase;
  color: var(--text-muted, #94a3b8);
}

.metric-icon {
  font-size: 18px;
  line-height: 1;
  opacity: 0.9;
}

.metric-value {
  font-size: 28px;
  font-weight: 800;
  letter-spacing: -0.6px;
  color: var(--text-strong, #ffffff);
  line-height: 1.15;
  margin-bottom: 8px;
  font-variant-numeric: tabular-nums;
  font-family: 'Plus Jakarta Sans', system-ui, sans-serif;
}

.variant-primary .metric-value {
  background: linear-gradient(135deg, #ffffff 40%, #38bdf8 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
}

.variant-emerald .metric-value {
  background: linear-gradient(135deg, #ffffff 40%, #34d399 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
}

.variant-purple .metric-value {
  background: linear-gradient(135deg, #ffffff 40%, #c084fc 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
}

.variant-amber .metric-value {
  background: linear-gradient(135deg, #ffffff 40%, #fbbf24 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
}

.metric-sub {
  font-size: 12.5px;
  color: var(--text-muted, #94a3b8);
  display: flex;
  align-items: center;
  gap: 6px;
}

.metric-sub-text {
  font-weight: 500;
}
</style>
