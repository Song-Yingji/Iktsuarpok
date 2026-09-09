<script setup>
import Icon from '../Icon.vue'
defineProps({
  variant: { type: String, default: 'primary' },
  size: { type: String, default: '' },
  icon: { type: String, default: '' },
  className: { type: String, default: '' },
  loading: { type: Boolean, default: false },
  disabled: { type: Boolean, default: false }
})
</script>

<template>
  <button
    :class="['btn', 'btn-' + variant, size && 'btn-' + size, loading && 'btn-loading', className]"
    :disabled="loading || disabled"
  >
    <span v-if="loading" class="spinner" />
    <Icon v-else-if="icon" :name="icon" :size="15" />
    <slot />
  </button>
</template>