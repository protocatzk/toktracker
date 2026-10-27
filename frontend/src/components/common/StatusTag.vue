<template>
  <span :class="['status-tag', tagClass]" :title="title">
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
    return "live";
  }
  if (
    props.state === "polling_offline" ||
    props.state === "connecting" ||
    props.state === "backoff"
  ) {
    return "polling";
  }
  if (props.state === "error" || props.state === "failed") {
    return "danger";
  }
  return "";
});
</script>
