<script setup>
defineProps({
  checked: { type: Boolean, default: false },
  disabled: { type: Boolean, default: false }
})
const emit = defineEmits(['change'])
</script>

<template>
  <button
    type="button"
    :class="['toggle', checked && 'on', disabled && 'disabled']"
    :aria-pressed="checked"
    @click="!disabled && emit('change', !checked)"
  >
    <span class="toggle-knob" />
  </button>
</template>