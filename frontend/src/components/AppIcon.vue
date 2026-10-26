<script setup lang="ts">
/**
 * Lucide SVG 图标统一尺寸与描边(Hallmark:不用 emoji 当图标)。
 * 用法:<AppIcon :icon="MessageSquare" /> 或传入任意 Lucide 组件。
 */
import type { Component } from 'vue'

withDefaults(
  defineProps<{
    icon: Component
    size?: number
    strokeWidth?: number
  }>(),
  {
    size: 18,
    strokeWidth: 1.75,
  },
)
</script>

<template>
  <component
    :is="icon"
    class="app-icon"
    :size="size"
    :stroke-width="strokeWidth"
    aria-hidden="true"
  />
</template>

<style scoped>
.app-icon {
  display: inline-block;
  flex-shrink: 0;
  vertical-align: middle;
  color: currentColor;
}
</style>
