<script setup>
defineProps({
  tone: { type: String, default: 'neutral' },
  dot: { type: Boolean, default: false }
})
</script>

<template>
  <span :class="['badge', 'badge-' + tone]">
    <i v-if="dot" class="badge-dot" />
    <slot />
  </span>
</template>