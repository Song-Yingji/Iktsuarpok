<script setup>
import { ref, reactive, onMounted } from 'vue'
import { adminApi } from '../../api'
import { Card, Button, Toggle, Slider } from '../ui'

// 与后端 modular_rag.DEFAULT_CONFIG 保持一致，供「恢复默认」使用
const DEFAULTS = {
  enable_rewrite: false,
  enable_fusion: true,
  fusion_method: 'rrf',
  enable_rerank: true,
  enable_compression: false,
  enable_self_rag: false,
  rewrite_method: 'multi',
  top_k: 4,
  min_score: 0.3
}

const MODULES = [
  { key: 'enable_rewrite', label: '查询改写', desc: '规则式多查询（疑问句变体 + 关键词扩展），提升召回率' },
  { key: 'enable_fusion', label: '多路融合', desc: '向量检索 + BM25 关键词检索，经 RRF 倒数排序融合' },
  { key: 'enable_rerank', label: '重排序', desc: '按分词重叠与短语匹配，对检索结果重新打分排序' },
  { key: 'enable_compression', label: '上下文压缩', desc: '分句打分，仅保留与问题最相关的句子，精简上下文' },
  { key: 'enable_self_rag', label: '本地大模型分析（Self-RAG）', desc: '调用本地大模型判定是否需要检索、检索内容是否有用，过滤无效上下文' }
]

const FUSION_METHODS = [
  { value: 'rrf', label: 'RRF 倒数排序融合' },
  { value: 'weighted', label: '加权融合' },
  { value: 'concat', label: '直接拼接（去重）' }
]

const REWRITE_METHODS = [
  { value: 'multi', label: '多查询（疑问句变体 + 关键词）' },
  { value: 'expand', label: '同义词扩展' }
]

const loading = ref(true)
const saving = ref(false)
const error = ref('')
const saved = ref(false)

const form = reactive({ ...DEFAULTS })

async function load() {
  loading.value = true
  error.value = ''
  try {
    Object.assign(form, await adminApi.ragConfig())
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

async function save() {
  saving.value = true
  error.value = ''
  saved.value = false
  try {
    const cfg = await adminApi.saveRagConfig({
      ...form,
      top_k: Number(form.top_k) || 4,
      min_score: Number(form.min_score) || 0
    })
    Object.assign(form, cfg)
    saved.value = true
  } catch (e) {
    error.value = e.message
  } finally {
    saving.value = false
  }
}

async function reset() {
  Object.assign(form, DEFAULTS)
  await save()
}

onMounted(load)
</script>

<template>
  <div class="settings-wrap">
    <div v-if="error" class="admin-alert">{{ error }}</div>
    <div v-else-if="saved" class="admin-success">已保存，策略生成智能体的检索将立即按新配置生效</div>

    <div class="settings-grid">
      <Card title="模块开关" bodyClass="flush">
        <div v-if="loading" class="loading-state">加载中…</div>
        <div v-else class="module-list">
          <div v-for="m in MODULES" :key="m.key" class="module-row">
            <div class="module-info">
              <strong>{{ m.label }}</strong>
              <p>{{ m.desc }}</p>
            </div>
            <div class="module-pipe">
              <span class="pipe-state" :class="form[m.key] ? 'on' : 'off'">
                {{ form[m.key] ? '已接入' : '已拔出' }}
              </span>
              <Toggle :checked="form[m.key]" @change="(v) => (form[m.key] = v)" />
            </div>
          </div>
        </div>
      </Card>

      <Card title="检索参数" bodyClass="flush">
        <div v-if="loading" class="loading-state">加载中…</div>
        <div v-else class="param-list">
          <div class="field">
            <label class="field-label">融合方式 fusion_method</label>
            <select class="select" v-model="form.fusion_method">
              <option v-for="o in FUSION_METHODS" :key="o.value" :value="o.value">{{ o.label }}</option>
            </select>
          </div>
          <div class="field">
            <label class="field-label">改写方式 rewrite_method</label>
            <select class="select" v-model="form.rewrite_method">
              <option v-for="o in REWRITE_METHODS" :key="o.value" :value="o.value">{{ o.label }}</option>
            </select>
          </div>
          <div class="field">
            <label class="field-label">召回条数 Top-K</label>
            <Slider :value="Number(form.top_k)" :min="1" :max="20" :step="1" @change="(v) => (form.top_k = v)" />
            <span class="field-hint">最终拼入提示词的参考片段条数（1–20）</span>
          </div>
          <div class="field">
            <label class="field-label">相似度下限 min_score</label>
            <Slider :value="Number(form.min_score)" :min="0" :max="1" :step="0.05" @change="(v) => (form.min_score = v)" />
            <span class="field-hint">向量检索保留片段的最低余弦相似度（0–1）</span>
          </div>
        </div>
      </Card>
    </div>

    <div class="settings-actions">
      <Button variant="ghost" :disabled="loading || saving" @click="reset">恢复默认</Button>
      <Button :loading="saving" :disabled="loading" @click="save">保存配置</Button>
    </div>
  </div>
</template>

<style scoped>
.settings-grid {
  display: grid; grid-template-columns: 1fr 1fr; gap: 16px; align-items: start;
}
.module-list, .param-list { padding: 12px 16px; }
.module-row {
  display: flex; align-items: center; justify-content: space-between;
  gap: 14px; padding: 12px 0;
  border-bottom: 1px dashed rgba(32, 44, 71, 0.7);
}
.module-row:last-child { border-bottom: none; }
.module-info strong { font-size: 13.5px; font-weight: 600; display: block; }
.module-info p { font-size: 12px; color: var(--text-3); line-height: 1.6; margin-top: 3px; max-width: 320px; }
.module-pipe { display: flex; align-items: center; gap: 10px; flex-shrink: 0; }
.pipe-state {
  font-size: 11.5px; padding: 2px 8px; border-radius: 20px; border: 1px solid transparent;
}
.pipe-state.on { color: var(--accent-2); background: rgba(56, 225, 255, 0.1); border-color: rgba(56, 225, 255, 0.3); }
.pipe-state.off { color: var(--text-3); background: rgba(147, 161, 189, 0.1); border-color: rgba(147, 161, 189, 0.2); }

.param-list .field { margin-bottom: 16px; }
.param-list .field:last-child { margin-bottom: 4px; }

.loading-state { padding: 24px 16px; color: var(--text-3); font-size: 12.5px; }

.settings-actions {
  display: flex; justify-content: flex-end; gap: 10px; margin-top: 16px;
}

.admin-success {
  padding: 10px 14px; border-radius: 9px; margin-bottom: 16px;
  background: rgba(14, 203, 129, 0.1); border: 1px solid rgba(14, 203, 129, 0.35);
  color: var(--down); font-size: 12.5px;
}

@media (max-width: 900px) {
  .settings-grid { grid-template-columns: 1fr; }
}
</style>