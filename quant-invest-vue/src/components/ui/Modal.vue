<script setup>
import Icon from '../Icon.vue'
defineProps({
  open: { type: Boolean, default: false },
  title: { type: String, default: '' },
  width: { type: Number, default: 520 }
})
const emit = defineEmits(['close'])
</script>

<template>
  <div v-if="open" class="modal-mask" @click="emit('close')">
    <div class="modal" :style="{ width: width + 'px' }" @click.stop>
      <header class="modal-head">
        <h3><slot name="title">{{ title }}</slot></h3>
        <button class="modal-close" @click="emit('close')"><Icon name="close" :size="16" /></button>
      </header>
      <div class="modal-body"><slot /></div>
      <footer v-if="$slots.footer" class="modal-foot"><slot name="footer" /></footer>
    </div>
  </div>
</template>