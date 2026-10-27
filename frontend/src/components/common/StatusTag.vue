<template>
  <span :class="['status-badge', tagClass]" :title="title">
    <span class="status-pulse-dot" v-if="isLive || state === 'live' || state === 'connected'"></span>
    <slot>{{ label }}</slot>
  </span>
</template>

<script setup lang="ts">
import { computed } from "vue";

const props = withDefaults(
  defineProps<{
    state?: string;
    isLive?: boolean | number;
    label?: string;
    title?: string;
  }>(),
  {
    state: "stopped",
    isLive: false,
    label: "",
    title: "",
  }
);

const tagClass = computed(() => {
  if (props.isLive || props.state === "connected" || props.state === "live") {
    return "badge-live";
  }
  if (
    props.state === "polling_offline" ||
    props.state === "connecting" ||
    props.state === "backoff"
  ) {
    return "badge-polling";
  }
  if (props.state === "error" || props.state === "failed") {
    return "badge-danger";
  }
  return "badge-offline";
});
</script>

<style scoped>
.status-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border-radius: 9999px;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.5px;
  text-transform: uppercase;
  white-space: nowrap;
  transition: all 0.2s ease;
}

.badge-live {
  background: rgba(16, 185, 129, 0.15);
  border: 1px solid rgba(16, 185, 129, 0.4);
  color: #34d399;
  box-shadow: 0 0 12px rgba(16, 185, 129, 0.2);
}

.status-pulse-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #10b981;
  box-shadow: 0 0 6px #10b981;
  animation: pulseDot 1.8s infinite;
}

@keyframes pulseDot {
  0% { transform: scale(0.9); opacity: 0.8; }
  50% { transform: scale(1.3); opacity: 1; }
  100% { transform: scale(0.9); opacity: 0.8; }
}

.badge-polling {
  background: rgba(56, 189, 248, 0.12);
  border: 1px solid rgba(56, 189, 248, 0.35);
  color: #38bdf8;
}

.badge-offline {
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.08);
  color: #64748b;
}

.badge-danger {
  background: rgba(239, 68, 68, 0.15);
  border: 1px solid rgba(239, 68, 68, 0.35);
  color: #f87171;
}
</style>
