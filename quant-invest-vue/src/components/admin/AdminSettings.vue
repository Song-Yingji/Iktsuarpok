<script>
import { reactive } from 'vue'

// 模块级共享状态：测评的加载态/错误/结果跨页面切换不丢失（刷新浏览器后清空）
const evalState = reactive({ loading: false, error: '', result: null })
</script>

<script setup>
import { ref, reactive, computed, toRefs, onMounted } from 'vue'
import { adminApi } from '../../api'
import { useApp } from '../../store/app'
import { Card, Button, Toggle, Slider } from '../ui'

const { toast } = useApp()

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
  { key: 'enable_rewrite', label: '查询改写', desc: '规则式多查询（可选择改写方式）' },
  { key: 'enable_fusion', label: '多路融合', desc: '向量 + BM25 关键词，进行融合（可选择融合方式）' },
  { key: 'enable_rerank', label: '重排序', desc: '按分词重叠与短语匹配，对检索结果重新打分排序' },
  { key: 'enable_compression', label: '上下文压缩', desc: '分句打分，仅保留与问题最相关的句子，精简上下文' },
  { key: 'enable_self_rag', label: '本地大模型分析（Self-RAG）', desc: '判定是否需要检索、检索内容是否有用' }
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
  try {
    const cfg = await adminApi.saveRagConfig({
      ...form,
      top_k: Number(form.top_k) || 4,
      min_score: Number(form.min_score) || 0
    })
    Object.assign(form, cfg)
    toast('已保存配置')
    return true
  } catch (e) {
    error.value = e.message
    return false
  } finally {
    saving.value = false
  }
}

async function reset() {
  Object.assign(form, DEFAULTS)
  await save()
}

// ================= 效果测评（LlamaIndex） =================
const { loading: evalLoading, error: evalError, result: evalResult } = toRefs(evalState)
const evalForm = reactive({ numQuestions: 10, regenerate: false })
const datasetStatus = ref({ exists: false, size: 0, loaded: false })

// 题目数量超过已缓存题目数时，必须重新合成（无法复用缓存）
const needRegen = computed(() => {
  const cached = Number(datasetStatus.value.size) || 0
  return cached > 0 && Number(evalForm.numQuestions) > cached
})

const METRIC_CARDS = [
  { key: 'context_precision', label: '上下文精确率', en: 'Context Precision', desc: '标准 AP 公式\n按排名加权的平均精确率' },
  { key: 'context_recall', label: '上下文召回率', en: 'Context Recall', desc: '精确命中比例\n命中块数 ÷ 标准块总数' },
  { key: 'faithfulness', label: '忠实度', en: 'Faithfulness', desc: '陈述级归因\n计算支持的陈述数 ÷ 总陈述数' },
  { key: 'answer_relevance', label: '答案相关性', en: 'Answer Relevance', desc: 'LLM二值判断\n回答是否切题（是=1、否=0）' },
  { key: 'answer_correctness', label: '答案正确率', en: 'Answer Correctness', desc: 'rubric打分\n打1–5分，归一化到0–1区间' }
]

const EVAL_COUNTS = [5, 10, 15, 20]

async function refreshDatasetStatus() {
  try {
    const s = await adminApi.ragEvalDataset()
    datasetStatus.value = { ...s, loaded: true }
  } catch (e) {
    datasetStatus.value = { exists: false, size: 0, loaded: true }
  }
}

async function runEval() {
  // 先自动保存上方配置，确保测评按当前配置执行（保存失败则中止测评，绝不用旧配置先跑）
  const saved = await save()
  if (!saved) return
  evalState.loading = true
  evalState.error = ''
  try {
    const res = await adminApi.ragEval({
      numQuestions: Number(evalForm.numQuestions) || 10,
      regenerate: !!evalForm.regenerate || needRegen.value
    })
    evalState.result = res
    if (res.dataset && typeof res.dataset.size === 'number') {
      datasetStatus.value = { exists: true, size: res.dataset.size, loaded: true }
    }
    evalForm.regenerate = false
  } catch (e) {
    evalState.error = e.message
  } finally {
    evalState.loading = false
  }
}

function fmtMetric(v) {
  return v === null || v === undefined ? '—' : Number(v).toFixed(2)
}

function snippet(text) {
  const t = (text || '').replace(/\s+/g, ' ').trim()
  return t.length > 60 ? t.slice(0, 60) + '…' : t
}

function noteText(d) {
  return (d.errors || []).join('；') || '—'
}

onMounted(() => {
  load()
  refreshDatasetStatus()
})
</script>

<template>
  <div class="settings-wrap">
    <div v-if="error" class="admin-alert">{{ error }}</div>

    <div class="page-head">
      <div>
        <h1>模块设置</h1>
        <p>调整模块化 RAG 检索管线的模块插拔与检索参数</p>
      </div>
      <div class="page-actions">
        <Button variant="ghost" :disabled="loading || saving" @click="reset">恢复默认</Button>
        <Button :loading="saving" :disabled="loading" @click="save">保存配置</Button>
      </div>
    </div>

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
            <label class="field-label">改写方式 rewrite_method</label>
            <select class="select" v-model="form.rewrite_method">
              <option v-for="o in REWRITE_METHODS" :key="o.value" :value="o.value">{{ o.label }}</option>
            </select>
          </div>
          <div class="field">
            <label class="field-label">融合方式 fusion_method</label>
            <select class="select" v-model="form.fusion_method">
              <option v-for="o in FUSION_METHODS" :key="o.value" :value="o.value">{{ o.label }}</option>
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

    <div class="page-head eval-head">
      <div>
        <h1>效果测评</h1>
        <p>测评集由 LlamaIndex RagDatasetGenerator 从知识库自动合成（问题 + 标准答案 + 来源片段）。</p>
      </div>
      <div class="page-actions">
        <Button :loading="evalLoading" @click="runEval">开始测评</Button>
      </div>
    </div>

    <Card class="eval-bubble" bodyClass="flush">
      <div class="eval-params">
        <span class="eval-params-label">测评参数：</span>
        <span class="eval-params-item">
          <span class="eval-params-key">题目数量</span>
          <select class="select eval-select" v-model="evalForm.numQuestions">
            <option v-for="n in EVAL_COUNTS" :key="n" :value="n">{{ n }}</option>
          </select>
        </span>
        <span class="eval-params-item">
          <span class="eval-params-key">重新生成题目</span>
          <Toggle :checked="evalForm.regenerate || needRegen" :disabled="needRegen" @change="(v) => (evalForm.regenerate = v)" />
          <span v-if="needRegen" class="eval-regen-hint">题目数超过缓存（{{ datasetStatus.size }} 题），将重新合成</span>
        </span>
      </div>

      <div class="eval-divider"></div>

      <div class="eval-body">
        <div v-if="evalError" class="admin-alert">{{ evalError }}</div>
        <template v-if="evalResult">
          <div class="metric-grid">
            <div v-for="m in METRIC_CARDS" :key="m.key" class="metric-card">
              <div class="metric-head">
                <strong>{{ m.label }}</strong>
                <span class="metric-en">{{ m.en }}</span>
              </div>
              <div class="metric-value">{{ fmtMetric(evalResult.metrics[m.key]) }}</div>
              <p class="metric-desc">{{ m.desc }}</p>
            </div>
          </div>

          <div class="eval-meta">
            <span>评测集：{{ evalResult.dataset.used }} 题（{{ evalResult.dataset.regenerated ? '本次合成' : '复用缓存' }}）</span>
            <span>耗时：{{ evalResult.elapsedSeconds }} 秒</span>
          </div>

          <div class="eval-table-wrap">
            <table class="eval-table">
              <thead>
                <tr>
                  <th>问题</th>
                  <th>回答摘要</th>
                  <th>检索片段</th>
                  <th>精确率</th>
                  <th>召回率</th>
                  <th>忠实度</th>
                  <th>相关性</th>
                  <th>正确率</th>
                  <th>说明</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(d, i) in evalResult.details" :key="i">
                  <td class="cell-snippet" :title="d.query">{{ d.query }}</td>
                  <td class="cell-snippet" :title="d.answer">{{ snippet(d.answer) }}</td>
                  <td>{{ (d.contexts || []).length }} 条</td>
                  <td>{{ fmtMetric(d.contextPrecision) }}</td>
                  <td>{{ fmtMetric(d.contextRecall) }}</td>
                  <td>{{ fmtMetric(d.faithfulness) }}</td>
                  <td>{{ fmtMetric(d.answerRelevance) }}</td>
                  <td>
                    {{ fmtMetric(d.answerCorrectness) }}
                    <span v-if="d.answerCorrectnessRaw != null" class="metric-raw">({{ d.answerCorrectnessRaw }}/5)</span>
                  </td>
                  <td class="cell-note" :title="noteText(d)">{{ snippet(noteText(d)) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </template>
      </div>
    </Card>
  </div>
</template>

<style scoped>
.settings-grid {
  display: grid; grid-template-columns: 1fr 1fr; gap: 16px; align-items: stretch;
}
.settings-grid .card {
  height: 100%; display: flex; flex-direction: column;
}
.settings-grid :deep(.card-body) { flex: 1; display: flex; flex-direction: column; }
.module-list, .param-list { padding: 12px 16px; flex: 1; }
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

/* ---- 同级标题区块 ---- */
.eval-head { margin-top: 30px; }
.eval-params {
  display: flex; align-items: center; flex-wrap: wrap;
  gap: 8px; padding: 12px 16px; font-size: 12.5px;
}
.eval-params-label { color: var(--text-2); font-weight: 600; }
.eval-params-item { display: flex; align-items: center; gap: 8px; }
.eval-params-key { color: var(--text-3); }
.eval-regen-hint { color: var(--warn, #e6a23c); font-size: 11.5px; }
.eval-select { width: auto; min-width: 60px; padding: 5px 10px; font-size: 12.5px; }
.eval-divider { border-top: 1px dashed rgba(32, 44, 71, 0.7); }
.eval-body { padding: 16px; }
.metric-grid {
  display: grid; grid-template-columns: repeat(5, 1fr);
  gap: 12px; margin: 16px 0 12px;
}
.metric-card {
  display: flex; flex-direction: column;
  padding: 14px 16px; border-radius: 11px;
  background: rgba(255, 255, 255, 0.03); border: 1px solid var(--border-light);
}
.metric-head {
  display: flex; flex-direction: column; align-items: flex-start; gap: 2px;
}
.metric-head strong { font-size: 12.5px; font-weight: 600; white-space: nowrap; }
.metric-en { font-size: 10.5px; color: var(--text-3); white-space: nowrap; }
.metric-value {
  font-size: 22px; font-weight: 700; margin-top: 8px;
  font-variant-numeric: tabular-nums; letter-spacing: 0.2px;
}
.metric-desc {
  font-size: 11px; color: var(--text-3); line-height: 1.6; margin-top: auto; padding-top: 6px; white-space: pre-line;
}
.eval-meta {
  display: flex; gap: 18px; flex-wrap: wrap;
  font-size: 12px; color: var(--text-3); margin: 4px 0 12px;
}
.eval-table-wrap { overflow-x: auto; border: 1px solid var(--border-light); border-radius: 11px; }
.eval-table { width: 100%; border-collapse: collapse; font-size: 12px; min-width: 860px; }
.eval-table th {
  text-align: left; font-weight: 600; font-size: 11.5px; color: var(--text-3);
  padding: 9px 12px; border-bottom: 1px solid var(--border-light); white-space: nowrap;
}
.eval-table td {
  padding: 9px 12px; border-bottom: 1px solid var(--border-light);
  font-variant-numeric: tabular-nums;
}
.eval-table tr:last-child td { border-bottom: none; }
.eval-table .cell-snippet {
  max-width: 240px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.eval-table .cell-note {
  color: var(--text-3); max-width: 200px;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.metric-raw { color: var(--text-3); font-size: 11px; margin-left: 4px; }

@media (max-width: 900px) {
  .settings-grid { grid-template-columns: 1fr; }
  .metric-grid { grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); }
}
</style>