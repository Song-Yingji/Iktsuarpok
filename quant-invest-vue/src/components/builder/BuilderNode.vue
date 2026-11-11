<script setup>
import { computed } from 'vue'
import { Handle, Position, useVueFlow } from '@vue-flow/core'
import { NODE_DEFS, PORT_LABELS, nodeColor, paramSummary } from '../../lib/builderSchema'
import Icon from '../Icon.vue'

const props = defineProps({
  id: { type: String, required: true },
  type: { type: String, required: true },
  data: { type: Object, required: true },
  selected: { type: Boolean, default: false }
})

const def = computed(() => NODE_DEFS[props.type])
const color = computed(() => nodeColor(props.type))
const inputs = computed(() => Object.entries(def.value?.inputs || {}))
const outputs = computed(() => Object.entries(def.value?.outputs || {}))
const summary = computed(() => paramSummary(props.type, props.data?.params))

const { removeNodes } = useVueFlow()
</script>

<template>
  <div :class="['bnode', selected && 'selected', data.error && 'has-error']" :style="{ '--nc': color }">
    <div class="bnode-head">
      <span class="bnode-dot" />
      <span class="bnode-title">{{ def?.label || type }}</span>
      <button v-if="selected" class="bnode-del" title="删除节点" @click.stop="removeNodes([id])">
        <Icon name="close" :size="11" />
      </button>
    </div>
    <div v-if="summary" class="bnode-summary">{{ summary }}</div>
    <div class="bnode-ports">
      <div class="bnode-col">
        <div v-for="[port, pt] in inputs" :key="'in-' + port" class="bnode-port">
          <Handle type="target" :position="Position.Left" :id="port" :class="['bhandle', pt]" />
          <span>{{ PORT_LABELS[port] || port }}</span>
        </div>
      </div>
      <div class="bnode-col out">
        <div v-for="[port, pt] in outputs" :key="'out-' + port" class="bnode-port">
          <span>{{ PORT_LABELS[port] || port }}</span>
          <Handle type="source" :position="Position.Right" :id="port" :class="['bhandle', pt]" />
        </div>
      </div>
    </div>
    <div v-if="data.error" class="bnode-error" :title="data.error">{{ data.error }}</div>
  </div>
</template>

<style scoped>
.bnode {
  width: 172px;
  background: linear-gradient(180deg, var(--panel) 0%, #101728 100%);
  border: 1px solid var(--border-light);
  border-radius: 10px;
  font-size: 12px;
  color: var(--text);
  box-shadow: 0 4px 14px rgba(0, 0, 0, 0.35);
  transition: border-color 0.15s, box-shadow 0.15s;
}
.bnode.selected {
  border-color: var(--nc);
  box-shadow: 0 0 0 1px var(--nc), 0 6px 18px rgba(0, 0, 0, 0.45);
}
.bnode.has-error {
  border-color: var(--up);
  box-shadow: 0 0 0 1px var(--up), 0 4px 14px rgba(0, 0, 0, 0.35);
}
.bnode-head {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 8px 10px;
  border-bottom: 1px solid var(--border);
  border-left: 3px solid var(--nc);
  border-radius: 10px 10px 0 0;
}
.bnode-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--nc);
  flex-shrink: 0;
}
.bnode-title {
  flex: 1;
  font-weight: 600;
  font-size: 12.5px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.bnode-del {
  width: 18px;
  height: 18px;
  border: none;
  border-radius: 5px;
  background: transparent;
  color: var(--text-3);
  display: grid;
  place-items: center;
  padding: 0;
  flex-shrink: 0;
}
.bnode-del:hover {
  background: rgba(246, 70, 93, 0.15);
  color: var(--up);
}
.bnode-summary {
  padding: 5px 10px 0;
  color: var(--accent-2);
  font-size: 11px;
  font-variant-numeric: tabular-nums;
}
.bnode-ports {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  padding: 6px 0 8px;
}
.bnode-col {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}
.bnode-col.out {
  align-items: flex-end;
}
.bnode-port {
  position: relative;
  display: flex;
  align-items: center;
  padding: 2px 10px;
  color: var(--text-3);
  font-size: 10.5px;
  line-height: 1.4;
}
.bnode-port :deep(.vue-flow__handle) {
  width: 9px;
  height: 9px;
  border: 2px solid #0a0e17;
  border-radius: 50%;
}
.bnode-port :deep(.bhandle.series) {
  background: #4c8dff;
}
.bnode-port :deep(.bhandle.bool) {
  background: #a66bff;
}
.bnode-port :deep(.vue-flow__handle-left) {
  left: -5px;
}
.bnode-port :deep(.vue-flow__handle-right) {
  right: -5px;
}
.bnode-error {
  padding: 5px 10px;
  border-top: 1px solid rgba(246, 70, 93, 0.35);
  background: rgba(246, 70, 93, 0.1);
  color: var(--up);
  font-size: 10.5px;
  line-height: 1.45;
  border-radius: 0 0 10px 10px;
}
</style>