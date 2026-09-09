<script setup>
import Icon from '../Icon.vue'
defineProps({
  open: { type: Boolean, default: false },
  title: { type: String, default: '' },
  width: { type: Number, default: 760 }
})
const emit = defineEmits(['close'])
</script>

<template>
  <div :class="['drawer-mask', open && 'open']" @click="emit('close')">
    <div class="drawer" :style="{ width: width + 'px' }" @click.stop>
      <header class="drawer-head">
        <h3><slot name="title">{{ title }}</slot></h3>
        <button class="modal-close" @click="emit('close')"><Icon name="close" :size="16" /></button>
      </header>
      <div class="drawer-body"><slot /></div>
    </div>
  </div>
</template>