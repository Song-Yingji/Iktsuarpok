<script setup>
import { computed, useSlots } from 'vue'

const props = defineProps({
  title: { type: String, default: '' },
  className: { type: String, default: '' },
  bodyClass: { type: String, default: '' }
})
const slots = useSlots()
const hasTitle = computed(() => !!(props.title || slots.title))
</script>

<template>
  <section :class="['card', className]">
    <header v-if="hasTitle" class="card-head">
      <h3><slot name="title">{{ title }}</slot></h3>
      <div class="card-extra"><slot name="extra" /></div>
    </header>
    <div :class="['card-body', bodyClass]"><slot /></div>
  </section>
</template>