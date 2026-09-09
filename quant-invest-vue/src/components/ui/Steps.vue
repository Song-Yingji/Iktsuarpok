<script setup>
import Icon from '../Icon.vue'
defineProps({
  steps: { type: Array, default: () => [] },
  current: { type: Number, default: -1 }
})
</script>

<template>
  <div class="steps">
    <div v-for="(s, i) in steps" :key="s" :class="['step', i < current && 'done', i === current && 'active']">
      <span class="step-dot"><Icon v-if="i < current" name="check" :size="12" /><template v-else>{{ i + 1 }}</template></span>
      <span class="step-label">{{ s }}</span>
    </div>
  </div>
</template>