<script setup>
import { ref } from 'vue'
import { adminApi } from '../../api'
import { Card, Button, Badge } from '../ui'
import Icon from '../Icon.vue'

const query = ref('')
const topK = ref(4)
const searching = ref(false)
const error = ref('')
const results = ref(null)

async function doSearch() {
  const q = query.value.trim()
  if (!q) return
  searching.value = true
  error.value = ''
  results.value = null
  try {
    results.value = await adminApi.search({ query: q, topK: Number(topK.value) || 4 })
  } catch (e) {
    error.value = e.message
  } finally {
    searching.value = false
  }
}

function scoreTone(score) {
  if (score >= 0.75) return 'up'
  if (score >= 0.5) return 'warn'
  return 'neutral'
}
</script>

<template>
  <Card title="检索测试（模拟策略生成时的知识库召回）">
    <div class="search-row">
      <div class="search-box" style="flex: 1">
        <Icon name="search" :size="15" />
        <input
          class="input"
          placeholder="输入一个用户可能提出的问题，例如「MACD 金叉策略如何设置止损」"
          v-model="query"
          @keydown.enter="doSearch"
        />
      </div>
      <input
        class="input"
        type="number"
        min="1"
        max="20"
        style="width: 84px"
        title="召回条数 Top-K"
        v-model="topK"
      />
      <Button icon="search" :loading="searching" :disabled="!query.trim()" @click="doSearch">检索</Button>
    </div>

    <div v-if="error" class="admin-alert mt-16">{{ error }}</div>

    <div v-else-if="results" class="mt-16">
      <div v-if="!results.length" class="empty-state" style="padding: 28px 20px">
        <Icon name="search" :size="26" />
        <p>没有命中的片段，可尝试换个说法或先上传相关文档</p>
      </div>
      <div v-else class="hit-list">
        <div v-for="(h, i) in results" :key="i" class="hit">
          <div class="hit-head">
            <span class="hit-src">
              <Badge tone="info">#{{ i + 1 }}</Badge>
              《{{ h.docName }}》 · 第 {{ (h.chunkIndex ?? 0) + 1 }} 块
            </span>
            <Badge :tone="scoreTone(h.score)">相似度 {{ (h.score * 100).toFixed(1) }}%</Badge>
          </div>
          <p class="hit-text">{{ h.text }}</p>
        </div>
      </div>
    </div>
    <p v-else class="config-note">输入问题后点击检索，可预览策略生成智能体将召回的参考片段与相似度。</p>
  </Card>
</template>

<style scoped>
.search-row { display: flex; gap: 10px; align-items: flex-end; flex-wrap: wrap; }
.hit-list { display: flex; flex-direction: column; gap: 12px; }
.hit {
  border: 1px solid var(--border); border-radius: 10px;
  padding: 12px 14px; background: var(--bg-2);
}
.hit-head {
  display: flex; align-items: center; justify-content: space-between;
  gap: 10px; margin-bottom: 8px; flex-wrap: wrap;
}
.hit-src { display: inline-flex; align-items: center; gap: 8px; font-size: 12.5px; color: var(--text-2); }
.hit-text {
  font-size: 12.5px; color: var(--text-2); line-height: 1.75;
  white-space: pre-wrap;
}
.config-note { margin-top: 12px; font-size: 12px; color: var(--text-3); line-height: 1.7; }
</style>
