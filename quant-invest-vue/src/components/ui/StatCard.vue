<script setup>
import Icon from '../Icon.vue'
defineProps({
  label: { type: String, default: '' },
  value: { type: [String, Number], default: '' },
  sub: { type: [String, Number], default: '' },
  tone: { type: String, default: '' },
  icon: { type: String, default: '' }
})
</script>

<template>
  <div :class="['stat-card', tone && 'stat-' + tone]">
    <div class="stat-label">
      <Icon v-if="icon" :name="icon" :size="15" />
      {{ label }}
    </div>
    <div class="stat-value">{{ value }}</div>
    <div v-if="sub" class="stat-sub">{{ sub }}</div>
  </div>
</template>