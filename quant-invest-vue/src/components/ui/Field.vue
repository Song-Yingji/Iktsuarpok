<script setup>
defineProps({
  label: { type: String, default: '' },
  hint: { type: String, default: '' }
})
</script>

<template>
  <label class="field">
    <span class="field-label">{{ label }}</span>
    <slot />
    <span v-if="hint" class="field-hint">{{ hint }}</span>
  </label>
</template>