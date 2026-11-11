<script setup>
import { ref, computed, onMounted, watch, markRaw } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { VueFlow, useVueFlow } from '@vue-flow/core'
import { Background } from '@vue-flow/background'
import { Controls } from '@vue-flow/controls'
import '@vue-flow/core/dist/style.css'
import '@vue-flow/core/dist/theme-default.css'
import '@vue-flow/controls/dist/style.css'
import { strategyApi } from '../api'
import { useApp } from '../store/app'
import {
  NODE_DEFS, GROUPS, TEMPLATES, createNode, graphToFlow, flowToGraph, nodeColor, edgeColor
} from '../lib/builderSchema'
import BuilderNode from '../components/builder/BuilderNode.vue'
import { Button, Badge, Field, Modal } from '../components/ui'
import Icon from '../components/Icon.vue'

const route = useRoute()
const router = useRouter()
const { toast } = useApp()

const nodeTypes = Object.fromEntries(Object.keys(NODE_DEFS).map((t) => [t, markRaw(BuilderNode)]))
const typesOf = (gid) => Object.keys(NODE_DEFS).filter((t) => NODE_DEFS[t].group === gid)

const nodes = ref([])
const edges = ref([])
const name = ref('')
const editId = ref(null)
const selectedId = ref(null)
const errors = ref([])
const preview = ref(null)
const validating = ref(false)
const saveMode = ref('')
const templateOpen = ref(false)
const loading = ref(false)
const canvasRef = ref(null)

const { screenToFlowCoordinate, addNodes, addEdges, removeNodes, fitView, findNode } = useVueFlow()

const selectedNode = computed(() => nodes.value.find((n) => n.id === selectedId.value) || null)
const selectedDef = computed(() => (selectedNode.value ? NODE_DEFS[selectedNode.value.type] : null))

let edgeSeq = 0

function clearValidation() {
  errors.value = []
  preview.value = null
  for (const n of nodes.value) if (n.data.error) n.data.error = null
}

// ---------------- 拖拽 / 点击添加节点 ----------------
function onDragStart(e, type) {
  e.dataTransfer.setData('application/builder-node', type)
  e.dataTransfer.effectAllowed = 'move'
}
function onDragOver(e) {
  e.preventDefault()
  e.dataTransfer.dropEffect = 'move'
}
function onDrop(e) {
  const type = e.dataTransfer.getData('application/builder-node')
  if (!NODE_DEFS[type]) return
  const position = screenToFlowCoordinate({ x: e.clientX, y: e.clientY })
  const node = createNode(type, { x: position.x - 86, y: position.y - 20 })
  addNodes([node])
  selectedId.value = node.id
  clearValidation()
}
function addByClick(type) {
  const rect = canvasRef.value.getBoundingClientRect()
  const center = screenToFlowCoordinate({ x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 })
  const offset = (nodes.value.length % 5) * 30
  const node = createNode(type, { x: center.x - 86 + offset, y: center.y - 30 + offset })
  addNodes([node])
  selectedId.value = node.id
  clearValidation()
}

// ---------------- 连线 ----------------
function isValidConnection(conn, ctx) {
  const src = ctx?.sourceNode || findNode(conn.source)
  const dst = ctx?.targetNode || findNode(conn.target)
  if (!src || !dst || src.id === dst.id) return false
  const outType = NODE_DEFS[src.type]?.outputs[conn.sourceHandle]
  const inType = NODE_DEFS[dst.type]?.inputs[conn.targetHandle]
  if (!outType || !inType || outType !== inType) return false
  const list = ctx?.edges || edges.value
  return !list.some((e) => e.id !== conn.id && e.target === dst.id && e.targetHandle === conn.targetHandle)
}
function onConnect(conn) {
  const src = findNode(conn.source)
  const portType = NODE_DEFS[src.type]?.outputs[conn.sourceHandle]
  addEdges([{
    ...conn,
    id: `e${Date.now().toString(36)}_${edgeSeq++}`,
    type: 'smoothstep',
    style: { stroke: edgeColor(portType), strokeWidth: 1.6 }
  }])
  clearValidation()
}

// ---------------- 选中 / 删除 ----------------
function onNodeClick({ node }) {
  selectedId.value = node.id
}
function onPaneClick() {
  selectedId.value = null
}
function onNodesChange(changes) {
  const removed = changes.filter((c) => c.type === 'remove')
  if (!removed.length) return
  if (removed.some((c) => c.id === selectedId.value)) selectedId.value = null
  clearValidation()
}
function onEdgesChange(changes) {
  if (changes.some((c) => c.type === 'remove')) clearValidation()
}
function removeSelected() {
  if (!selectedId.value) return
  removeNodes([selectedId.value])
  selectedId.value = null
  clearValidation()
}

// ---------------- 校验 / 保存 ----------------
async function validate(notify = true) {
  validating.value = true
  try {
    const res = await strategyApi.validateBuilder(flowToGraph(nodes.value, edges.value))
    errors.value = res.errors || []
    const byId = {}
    for (const n of nodes.value) {
      n.data.error = null
      byId[n.id] = n
    }
    for (const e of errors.value) {
      const n = e.nodeId && byId[e.nodeId]
      if (n) n.data.error = n.data.error ? `${n.data.error}；${e.message}` : e.message
    }
    preview.value = res.ok ? { rules: res.rules, code: res.code } : null
    if (notify) {
      if (res.ok) toast('校验通过，可以保存策略')
      else toast(`发现 ${errors.value.length} 个问题，请查看右侧列表`, 'error')
    }
    return !!res.ok
  } catch (e) {
    toast(e.message, 'error')
    return false
  } finally {
    validating.value = false
  }
}

async function save(mode) {
  const trimmed = name.value.trim()
  if (!trimmed) return toast('请填写策略名称', 'error')
  const ok = await validate(false)
  if (!ok) return toast('校验未通过，请先修复画布中的问题', 'error')
  saveMode.value = mode
  try {
    const graph = flowToGraph(nodes.value, edges.value)
    const saved = editId.value
      ? await strategyApi.update(editId.value, { name: trimmed, params: graph })
      : await strategyApi.save({ name: trimmed, type: '自定义', engineId: 'builder', params: graph })
    editId.value = saved.id
    if (mode === 'backtest') {
      toast('已保存，正在前往回测')
      router.push({ path: '/strategy', query: { focus: saved.id } })
    } else {
      toast('策略已保存')
      router.replace(`/strategy/builder/${saved.id}`)
    }
  } catch (e) {
    toast(e.message, 'error')
  } finally {
    saveMode.value = ''
  }
}

function focusError(e) {
  if (!e.nodeId) return
  selectedId.value = e.nodeId
  fitView({ nodes: [e.nodeId], maxZoom: 1.1, padding: 0.6, duration: 300 })
}

// ---------------- 模板 / 编辑模式 ----------------
function loadTemplate(t) {
  const flow = graphToFlow(t.graph)
  nodes.value = flow.nodes
  edges.value = flow.edges
  if (!name.value.trim()) name.value = t.name
  selectedId.value = null
  clearValidation()
  templateOpen.value = false
  setTimeout(() => fitView({ padding: 0.2 }), 60)
}

async function init() {
  nodes.value = []
  edges.value = []
  selectedId.value = null
  errors.value = []
  preview.value = null
  name.value = ''
  editId.value = null
  const id = route.params.id ? Number(route.params.id) : null
  if (!id) return
  loading.value = true
  try {
    const list = await strategyApi.saved()
    const s = list.find((x) => x.id === id)
    if (!s || s.engineId !== 'builder') {
      toast('策略不存在或不是自由构建策略', 'error')
      router.replace('/strategy/builder')
      return
    }
    editId.value = s.id
    name.value = s.name
    const flow = graphToFlow(s.params)
    nodes.value = flow.nodes
    edges.value = flow.edges
    setTimeout(() => fitView({ padding: 0.2 }), 60)
  } catch (e) {
    toast(e.message, 'error')
  } finally {
    loading.value = false
  }
}

watch(() => route.params.id, (id) => {
  if (id && Number(id) === editId.value) return
  init()
})
onMounted(init)
</script>

<template>
  <div>
    <div class="page-head">
      <div>
        <h1>自由构建</h1>
        <p>拖拽节点搭建交易策略逻辑：数据源 → 指标 → 条件 → 买卖信号，校验通过后保存并回测</p>
      </div>
      <div class="page-actions">
        <Button variant="ghost" icon="strategy" @click="router.push('/strategy')">返回策略列表</Button>
        <Button v-if="editId" variant="ghost" icon="plus" @click="router.push('/strategy/builder')">新建策略</Button>
      </div>
    </div>

    <div class="builder-toolbar">
      <input class="input" style="width: 240px" v-model="name" placeholder="策略名称（必填）" maxlength="40" />
      <Badge :tone="editId ? 'warn' : 'info'">{{ editId ? '编辑已保存策略' : '新建策略' }}</Badge>
      <span style="flex: 1" />
      <Button variant="ghost" icon="doc" @click="templateOpen = true">载入模板</Button>
      <Button variant="ghost" icon="shield" :loading="validating" @click="validate(true)">校验</Button>
      <Button icon="check" :loading="saveMode === 'save'" :disabled="saveMode !== ''" @click="save('save')">保存</Button>
      <Button icon="bolt" :loading="saveMode === 'backtest'" :disabled="saveMode !== ''" @click="save('backtest')">保存并回测</Button>
    </div>

    <div class="builder-body">
      <aside class="builder-palette">
        <div class="palette-tip">拖拽节点到画布，或点击添加</div>
        <div v-for="g in GROUPS" :key="g.id" class="palette-group">
          <div class="palette-group-title"><i :style="{ background: g.color }" />{{ g.label }}</div>
          <div
            v-for="t in typesOf(g.id)"
            :key="t"
            class="palette-item"
            draggable="true"
            @dragstart="onDragStart($event, t)"
            @click="addByClick(t)"
          >
            <span class="palette-item-dot" :style="{ background: nodeColor(t) }" />
            {{ NODE_DEFS[t].label }}
          </div>
        </div>
      </aside>

      <div class="builder-canvas-wrap" ref="canvasRef">
        <VueFlow
          v-model:nodes="nodes"
          v-model:edges="edges"
          :node-types="nodeTypes"
          :is-valid-connection="isValidConnection"
          :delete-key-code="['Backspace', 'Delete']"
          :default-edge-options="{ type: 'smoothstep' }"
          :min-zoom="0.3"
          :max-zoom="1.8"
          :edges-updatable="false"
          @connect="onConnect"
          @drop="onDrop"
          @dragover="onDragOver"
          @node-click="onNodeClick"
          @pane-click="onPaneClick"
          @nodes-change="onNodesChange"
          @edges-change="onEdgesChange"
        >
          <Background :gap="18" :size="1.2" color="#1b2540" />
          <Controls :show-interactive="false" position="bottom-left" />
        </VueFlow>
        <div v-if="loading" class="canvas-empty"><p>策略加载中…</p></div>
        <div v-else-if="!nodes.length" class="canvas-empty">
          <Icon name="sliders" :size="30" />
          <p>从左侧拖入节点开始构建，或点击「载入模板」快速开始</p>
        </div>
      </div>

      <aside class="builder-side">
        <section class="side-sec">
          <h4>
            <template v-if="selectedNode">
              <i :style="{ background: nodeColor(selectedNode.type) }" />{{ selectedDef.label }} · 参数
            </template>
            <template v-else>节点参数</template>
          </h4>
          <template v-if="selectedNode">
            <Field
              v-for="(spec, key) in selectedDef.params"
              :key="key"
              :label="spec.label"
              :hint="`范围 ${spec.min} ~ ${spec.max}`"
            >
              <input
                class="input"
                type="number"
                :step="spec.kind === 'int' ? 1 : 0.1"
                :min="spec.min"
                :max="spec.max"
                v-model.number="selectedNode.data.params[key]"
                @input="clearValidation"
              />
            </Field>
            <div v-if="!Object.keys(selectedDef.params).length" class="side-empty">该节点无可调参数</div>
            <Button size="sm" variant="danger" icon="trash" @click="removeSelected">删除节点</Button>
          </template>
          <div v-else class="side-empty">点击画布中的节点编辑参数</div>
        </section>

        <section class="side-sec">
          <h4>校验结果</h4>
          <div v-if="preview" class="side-ok"><Icon name="check" :size="14" />校验通过，可以保存</div>
          <ul v-else-if="errors.length" class="side-errors">
            <li v-for="(e, i) in errors" :key="i" :class="{ clickable: !!e.nodeId }" @click="focusError(e)">
              <Icon name="close" :size="12" />{{ e.message }}
            </li>
          </ul>
          <div v-else class="side-empty">尚未校验，点击「校验」检查连线逻辑</div>
        </section>

        <section v-if="preview" class="side-sec">
          <h4>规则预览</h4>
          <ul class="side-rules">
            <li v-for="(r, i) in preview.rules" :key="i">{{ r }}</li>
          </ul>
          <pre class="side-code">{{ preview.code }}</pre>
        </section>

        <section class="side-sec">
          <h4>操作提示</h4>
          <ul class="side-tips">
            <li>从节点右侧端口拖到另一节点左侧端口即可连线</li>
            <li>蓝色端口为数值序列，紫色端口为布尔信号，同类才能相连</li>
            <li>选中节点或连线后按 Delete 键删除</li>
            <li>策略需同时包含买入与卖出信号节点</li>
          </ul>
        </section>
      </aside>
    </div>

    <Modal :open="templateOpen" title="载入策略模板" :width="560" @close="templateOpen = false">
      <div v-if="nodes.length" class="admin-alert warn" style="margin-bottom: 14px">
        载入模板将替换当前画布内容
      </div>
      <div class="tpl-list">
        <div v-for="t in TEMPLATES" :key="t.id" class="tpl-card">
          <div>
            <h4>{{ t.name }}</h4>
            <p>{{ t.desc }}</p>
          </div>
          <Button size="sm" icon="plus" @click="loadTemplate(t)">载入</Button>
        </div>
      </div>
      <template #footer>
        <Button variant="ghost" @click="templateOpen = false">取消</Button>
      </template>
    </Modal>
  </div>
</template>

<style scoped>
.builder-toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  padding: 12px 14px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--panel);
  margin-bottom: 12px;
}
.builder-body {
  display: flex;
  gap: 12px;
  height: calc(100vh - 288px);
  min-height: 460px;
}

/* 左侧节点面板 */
.builder-palette {
  width: 186px;
  flex-shrink: 0;
  overflow-y: auto;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--panel);
  padding: 10px;
}
.palette-tip {
  font-size: 11px;
  color: var(--text-3);
  padding: 2px 4px 10px;
  line-height: 1.5;
}
.palette-group { margin-bottom: 12px; }
.palette-group-title {
  display: flex;
  align-items: center;
  gap: 7px;
  font-size: 11.5px;
  color: var(--text-2);
  font-weight: 600;
  padding: 0 4px 6px;
  letter-spacing: 0.5px;
}
.palette-group-title i {
  width: 7px;
  height: 7px;
  border-radius: 50%;
}
.palette-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 7px 9px;
  margin: 3px 0;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg-2);
  font-size: 12.5px;
  color: var(--text-2);
  cursor: grab;
  transition: all 0.15s;
  user-select: none;
}
.palette-item:hover {
  border-color: var(--accent);
  color: var(--text);
  transform: translateX(2px);
}
.palette-item:active { cursor: grabbing; }
.palette-item-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex-shrink: 0;
}

/* 画布 */
.builder-canvas-wrap {
  flex: 1;
  min-width: 0;
  position: relative;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  overflow: hidden;
  background: var(--bg-2);
}
.builder-canvas-wrap :deep(.vue-flow) {
  width: 100%;
  height: 100%;
}
.builder-canvas-wrap :deep(.vue-flow__node) {
  cursor: grab;
}
.builder-canvas-wrap :deep(.vue-flow__node.dragging) {
  cursor: grabbing;
}
.builder-canvas-wrap :deep(.vue-flow__edge-path) {
  stroke-width: 1.6;
}
.builder-canvas-wrap :deep(.vue-flow__edge.selected .vue-flow__edge-path) {
  stroke: var(--accent-2);
  stroke-width: 2.4;
}
.builder-canvas-wrap :deep(.vue-flow__edge:hover .vue-flow__edge-path) {
  stroke-width: 2.4;
}
.builder-canvas-wrap :deep(.vue-flow__connection-path) {
  stroke: var(--accent-2);
  stroke-width: 1.8;
}
.builder-canvas-wrap :deep(.vue-flow__controls) {
  box-shadow: none;
  border: 1px solid var(--border);
  border-radius: 8px;
  overflow: hidden;
}
.builder-canvas-wrap :deep(.vue-flow__controls-button) {
  background: var(--panel-2);
  border-bottom: 1px solid var(--border);
  color: var(--text-2);
  width: 26px;
  height: 26px;
}
.builder-canvas-wrap :deep(.vue-flow__controls-button:hover) {
  background: var(--panel);
  color: var(--text);
}
.builder-canvas-wrap :deep(.vue-flow__controls-button svg) {
  fill: currentColor;
}
.canvas-empty {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  color: var(--text-3);
  font-size: 13px;
  pointer-events: none;
  text-align: center;
  padding: 20px;
}
.canvas-empty svg { opacity: 0.5; }

/* 右侧面板 */
.builder-side {
  width: 288px;
  flex-shrink: 0;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.side-sec {
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--panel);
  padding: 13px 14px;
}
.side-sec h4 {
  display: flex;
  align-items: center;
  gap: 7px;
  font-size: 13px;
  margin-bottom: 10px;
}
.side-sec h4 i {
  width: 7px;
  height: 7px;
  border-radius: 50%;
}
.side-sec :deep(.field) { margin-bottom: 12px; }
.side-empty {
  font-size: 12px;
  color: var(--text-3);
  line-height: 1.6;
  padding: 2px 0;
}
.side-ok {
  display: flex;
  align-items: center;
  gap: 7px;
  font-size: 12.5px;
  color: var(--down);
}
.side-errors {
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 7px;
}
.side-errors li {
  display: flex;
  gap: 7px;
  align-items: flex-start;
  font-size: 12px;
  line-height: 1.5;
  color: var(--up);
  padding: 7px 9px;
  border-radius: 7px;
  background: rgba(246, 70, 93, 0.08);
  border: 1px solid rgba(246, 70, 93, 0.25);
}
.side-errors li svg { flex-shrink: 0; margin-top: 2px; }
.side-errors li.clickable { cursor: pointer; }
.side-errors li.clickable:hover { background: rgba(246, 70, 93, 0.16); }
.side-rules {
  margin: 0 0 10px;
  padding-left: 17px;
  color: var(--text-2);
  font-size: 12px;
  line-height: 1.7;
}
.side-code {
  background: #0a1120;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 10px;
  overflow-x: auto;
  font-family: 'JetBrains Mono', Consolas, monospace;
  font-size: 11px;
  color: #a9d8ff;
  line-height: 1.6;
  white-space: pre-wrap;
}
.side-tips {
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.side-tips li {
  font-size: 11.5px;
  color: var(--text-3);
  line-height: 1.55;
  padding-left: 14px;
  position: relative;
}
.side-tips li::before {
  content: '';
  position: absolute;
  left: 2px;
  top: 7px;
  width: 4px;
  height: 4px;
  border-radius: 50%;
  background: var(--accent-2);
}

/* 模板弹窗 */
.tpl-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.tpl-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  padding: 13px 14px;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--bg-2);
}
.tpl-card h4 { font-size: 13.5px; margin-bottom: 4px; }
.tpl-card p { font-size: 12px; color: var(--text-2); line-height: 1.6; }

/* 窄屏：纵向堆叠，保证画布始终有可用宽高 */
@media (max-width: 1100px) {
  .builder-body {
    flex-direction: column;
    height: auto;
  }
  .builder-palette {
    width: 100%;
    display: flex;
    flex-wrap: wrap;
    gap: 4px 18px;
    align-items: flex-start;
  }
  .palette-tip { width: 100%; padding-bottom: 4px; }
  .palette-group { margin-bottom: 4px; }
  .builder-canvas-wrap {
    flex: none;
    width: 100%;
    height: 420px;
  }
  .builder-side {
    width: 100%;
    flex-direction: row;
    flex-wrap: wrap;
  }
  .side-sec { flex: 1 1 260px; }
}
</style>