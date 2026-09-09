<script setup>
import Icon from '../Icon.vue'
defineProps({
  text: { type: String, default: '暂无数据' }
})
</script>

<template>
  <div class="empty-state"><Icon name="chart" :size="28" /><p>{{ text }}</p></div>
</template>