<script setup>
import * as echarts from 'echarts'
import { ref, onMounted, onBeforeUnmount, watch } from 'vue'

const props = defineProps({
  option: { type: Object, default: null },
  onClick: { type: Function, default: null }
})
const emit = defineEmits(['click'])

const el = ref(null)
let chart = null
let ro = null

onMounted(() => {
  chart = echarts.init(el.value)
  if (props.onClick) chart.on('click', props.onClick)
  chart.on('click', (params) => emit('click', params))
  if (props.option) chart.setOption(props.option, true)
  ro = new ResizeObserver(() => chart && chart.resize())
  ro.observe(el.value)
})

onBeforeUnmount(() => {
  ro && ro.disconnect()
  chart && chart.dispose()
})

watch(
  () => props.option,
  (opt) => {
    if (chart && opt) chart.setOption(opt, true)
  },
  { deep: true }
)
</script>

<template>
  <div ref="el"></div>
</template>