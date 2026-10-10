<script setup>
import { ref, computed, onMounted } from 'vue'
import { adminApi } from '../../api'
import { useAdminKb } from '../../store/admin'
import { fmt } from '../../lib/utils'
import { Card, Button, Modal } from '../ui'
import Icon from '../Icon.vue'

const ACCEPT = '.txt,.md,.markdown,.csv,.log,.pdf,.docx'
const MAX_MB = 10

const { kbStats: stats, loadKbStats } = useAdminKb()
const docs = ref([])
const loading = ref(true)
const error = ref('')

const uploadOpen = ref(false)
const uploadError = ref('')
const uploading = ref(false)
const uploadingName = ref('')
const dragging = ref(false)
const fileInput = ref(null)
const pending = ref([])

const ready = computed(() => stats.value?.ready !== false)

function openUpload() {
  uploadError.value = ''
  pending.value = []
  uploadOpen.value = true
}

// 退出上传界面后自动刷新一次文档列表
function closeUpload() {
  uploadOpen.value = false
  refresh()
}

async function refresh() {
  loading.value = true
  error.value = ''
  try {
    const [, d] = await Promise.all([loadKbStats(true), adminApi.docs()])
    docs.value = d
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

function pickFile() {
  if (uploading.value) return
  fileInput.value?.click()
}

function onPick(e) {
  const files = e.target.files
  if (files?.length) addFiles(files)
  e.target.value = ''
}

function onDrop(e) {
  dragging.value = false
  const files = e.dataTransfer?.files
  if (files?.length) addFiles(files)
}

// 选中的文件先入待传队列，点击「确认」后才真正入库
function addFiles(fileList) {
  if (uploading.value) return
  uploadError.value = ''
  for (const file of Array.from(fileList)) {
    if (file.size > MAX_MB * 1024 * 1024) {
      uploadError.value = `《${file.name}》超过 ${MAX_MB}MB，已跳过`
      continue
    }
    pending.value.push(file)
  }
}

async function confirmUpload() {
  if (!pending.value.length || uploading.value) return
  uploading.value = true
  uploadError.value = ''
  for (const file of [...pending.value]) {
    uploadingName.value = file.name
    try {
      const doc = await adminApi.upload(file)
      docs.value = [doc, ...docs.value.filter((d) => d.id !== doc.id)]
      pending.value = pending.value.filter((f) => f !== file)
    } catch (e) {
      uploadError.value = `《${file.name}》入库失败：${e.message}`
    }
  }
  uploading.value = false
  uploadingName.value = ''
  await loadKbStats(true)
  if (!uploadError.value) closeUpload()
}

async function removeDoc(doc) {
  if (!confirm(`确定删除《${doc.name}》及其 ${doc.chunks} 个分块吗？`)) return
  try {
    await adminApi.removeDoc(doc.id)
    docs.value = docs.value.filter((d) => d.id !== doc.id)
    await loadKbStats(true)
  } catch (e) {
    error.value = e.message
  }
}

onMounted(refresh)
</script>

<template>
  <div>
    <div v-if="error" class="admin-alert">{{ error }}</div>
    <div v-if="stats && !ready" class="admin-alert warn">
      尚未配置向量化模型 API Key，请在后端 llm_config.py 中填写 EMBED_API_KEY 后重启服务，否则无法建立索引与检索。
    </div>

    <div class="grid grid-2">
      <Card title="知识库概览">
        <div class="kv-list">
          <div class="kv-row"><span class="k">已入库文档</span><span>{{ stats ? stats.docs : '--' }}</span></div>
          <div class="kv-row"><span class="k">向量分块总数</span><span>{{ stats ? stats.chunks : '--' }}</span></div>
        </div>
      </Card>
      <Card title="向量模型">
        <div class="kv-list">
          <div class="kv-row"><span class="k">向量模型</span><span>{{ stats?.model || '--' }}</span></div>
          <div class="kv-row"><span class="k">向量维度</span><span>{{ stats?.dim || '--' }}</span></div>
        </div>
      </Card>
    </div>

    <Card class="mt-16" :title="`文档列表（${docs.length}）`" bodyClass="flush">
      <template #extra>
        <Button size="sm" icon="upload" @click="openUpload">上传文档</Button>
      </template>
      <div v-if="loading" class="admin-empty">加载中…</div>
      <div v-else-if="!docs.length" class="empty-state">
        <Icon name="doc" :size="28" />
        <p>暂无文档，点击右上角「上传文档」建立索引</p>
      </div>
      <div v-else style="overflow-x: auto">
        <table class="data-table">
          <thead>
            <tr>
              <th>文档名称</th>
              <th class="num">分块数</th>
              <th class="num">字符数</th>
              <th>入库时间</th>
              <th style="width: 90px"></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="d in docs" :key="d.id">
              <td>
                <span class="doc-name"><Icon name="doc" :size="14" />{{ d.name }}</span>
              </td>
              <td class="num">{{ d.chunks }}</td>
              <td class="num">{{ fmt.num(d.chars, 0) }}</td>
              <td>{{ d.createdAt }}</td>
              <td>
                <Button size="sm" variant="danger" icon="trash" @click="removeDoc(d)">删除</Button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </Card>

    <Modal :open="uploadOpen" title="上传文档" :width="560" @close="closeUpload">
      <div v-if="uploadError" class="admin-alert">{{ uploadError }}</div>

      <div v-if="pending.length" class="pending-list">
        <div v-for="(f, i) in pending" :key="i" class="pending-item">
          <Icon name="doc" :size="13" />
          <span class="pending-name">{{ f.name }}</span>
          <span class="pending-size">{{ fmt.size(f.size) }}</span>
          <button class="pending-del" :disabled="uploading" @click="pending.splice(i, 1)">
            <Icon name="close" :size="12" />
          </button>
        </div>
      </div>

      <div
        :class="['dropzone', dragging && 'dragging', uploading && 'busy']"
        @click="pickFile"
        @dragover.prevent="dragging = true"
        @dragleave.prevent="dragging = false"
        @drop.prevent="onDrop"
      >
        <input ref="fileInput" type="file" :accept="ACCEPT" multiple hidden @change="onPick" />
        <span class="dropzone-icon"><Icon :name="uploading ? 'refresh' : 'upload'" :size="26" /></span>
        <p class="dropzone-title">
          {{
            uploading
              ? `正在上传《${uploadingName}》…`
              : pending.length
                ? '已选择文件，可继续点击或拖拽添加'
                : '点击选择或拖拽文件到此处'
          }}
        </p>
        <p class="dropzone-hint">支持 txt / md / csv / log / pdf / docx，单文件不超过 {{ MAX_MB }}MB，可多选</p>
        <div v-if="uploading" class="progress"><i /></div>
      </div>

      <div class="upload-steps">
        <div class="up-step"><b>1</b> 文本抽取</div>
        <div class="up-step"><b>2</b> 递归分块</div>
        <div class="up-step"><b>3</b> 向量化</div>
        <div class="up-step"><b>4</b> 写入 Chroma</div>
      </div>

      <template #footer>
        <Button :loading="uploading" :disabled="!pending.length" @click="confirmUpload">
          确认{{ pending.length ? `（${pending.length}）` : '' }}
        </Button>
      </template>
    </Modal>
  </div>
</template>

<style scoped>
.dropzone {
  display: flex; flex-direction: column; align-items: center; gap: 6px;
  padding: 34px 20px; text-align: center; cursor: pointer;
  border: 1.5px dashed var(--border-light); border-radius: 12px;
  background: var(--bg-2); transition: all 0.18s;
}

.dropzone:hover { border-color: var(--accent); background: rgba(76, 141, 255, 0.05); }
.dropzone.dragging { border-color: var(--accent); background: var(--accent-soft); }
.dropzone.busy { cursor: progress; }
.dropzone-icon {
  width: 52px; height: 52px; border-radius: 14px;
  display: grid; place-items: center; margin-bottom: 6px;
  background: var(--accent-soft); color: var(--accent-2);
}
.dropzone.busy .dropzone-icon svg { animation: spin 0.9s linear infinite; }
.dropzone-title { font-size: 14px; font-weight: 600; }
.dropzone-hint { font-size: 12px; color: var(--text-3); }
.progress {
  width: 70%; height: 4px; border-radius: 4px; overflow: hidden;
  background: var(--panel-2); margin-top: 10px;
}
.progress i {
  display: block; width: 40%; height: 100%;
  background: linear-gradient(90deg, var(--accent), var(--accent-2));
  animation: slide 1.1s ease-in-out infinite;
}
@keyframes slide {
  0% { transform: translateX(-100%); }
  100% { transform: translateX(250%); }
}

.pending-list {
  margin-bottom: 14px; border: 1px solid var(--border); border-radius: 10px;
  max-height: 168px; overflow-y: auto;
}
.pending-item {
  display: flex; align-items: center; gap: 8px;
  padding: 8px 12px; font-size: 12.5px;
}
.pending-item + .pending-item { border-top: 1px solid var(--border); }
.pending-item > svg { flex: 0 0 auto; color: var(--accent-2); }
.pending-name {
  flex: 1 1 auto; min-width: 0; color: var(--text);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.pending-size {
  flex: 0 0 auto; color: var(--text-3);
  font-family: 'JetBrains Mono', Consolas, monospace; font-size: 11.5px;
}
.pending-del {
  flex: 0 0 auto; display: inline-flex; padding: 2px;
  border: 0; background: none; color: var(--text-3); cursor: pointer;
}
.pending-del:hover:not(:disabled) { color: var(--up); }
.pending-del:disabled { opacity: 0.4; cursor: not-allowed; }

.upload-steps { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 14px; }
.up-step {
  display: flex; align-items: center; gap: 6px;
  font-size: 11.5px; color: var(--text-3);
}
.up-step b {
  width: 18px; height: 18px; border-radius: 50%;
  display: grid; place-items: center; font-size: 10.5px;
  background: var(--panel-2); border: 1px solid var(--border); color: var(--text-2);
}

.doc-name { display: inline-flex; align-items: center; gap: 7px; font-weight: 600; }
.doc-name svg { color: var(--accent-2); }
.admin-empty { padding: 30px; text-align: center; color: var(--text-3); font-size: 13px; }
</style>
