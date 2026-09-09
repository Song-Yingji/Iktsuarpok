<script setup>
defineProps({
  value: { type: Number, default: 0 },
  min: { type: Number, default: 0 },
  max: { type: Number, default: 100 },
  step: { type: Number, default: 1 },
  suffix: { type: String, default: '' }
})
const emit = defineEmits(['change'])
</script>

<template>
  <div class="slider-row">
    <input
      type="range" :min="min" :max="max" :step="step" :value="value"
      @input="emit('change', +$event.target.value)"
    />
    <span class="slider-value">{{ value }}{{ suffix }}</span>
  </div>
</template>