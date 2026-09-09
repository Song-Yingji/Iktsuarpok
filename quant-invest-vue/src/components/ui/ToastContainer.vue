<script setup>
import Icon from '../Icon.vue'
defineProps({
  toasts: { type: Array, default: () => [] }
})
</script>

<template>
  <div class="toast-wrap">
    <div v-for="t in toasts" :key="t.id" :class="['toast', 'toast-' + t.type]">
      <Icon :name="t.type === 'error' ? 'close' : 'check'" :size="15" />
      {{ t.msg }}
    </div>
  </div>
</template>