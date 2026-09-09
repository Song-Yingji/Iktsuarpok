<script setup>
defineProps({
  active: { type: Boolean, default: false }
})
const emit = defineEmits(['click'])
</script>

<template>
  <button type="button" :class="['chip', active && 'chip-active']" @click="emit('click')">
    <slot />
  </button>
</template>