<script setup>
import { ref, watch, onMounted } from 'vue'
import { newsApi } from '../api'
import { Card, Chip, Modal, Badge } from '../components/ui'
import Icon from '../components/Icon.vue'
import { useApp } from '../store/app'

const sentimentTone = { 利好: 'up', 利空: 'down', 中性: 'neutral' }

const { newsCategories } = useApp()

const list = ref([])
const category = ref('全部')
const keyword = ref('')
const detail = ref(null)

const load = () => newsApi.list({ category: category.value, keyword: keyword.value }).then((d) => (list.value = d))

onMounted(load)
watch([category, keyword], load)
</script>

<template>
  <div>
    <div class="page-head">
      <div>
        <h1>财经新闻</h1>
        <p>7×24 小时全球财经快讯 · AI 情绪识别（利好 / 利空 / 中性）</p>
      </div>
      <div class="search-box" style="width: 240px">
        <Icon name="search" :size="15" />
        <input class="input" placeholder="搜索新闻关键词" v-model="keyword" />
      </div>
    </div>

    <div style="display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 16px">
      <Chip v-for="c in newsCategories" :key="c" :active="category === c" @click="category = c">{{ c }}</Chip>
    </div>

    <Card bodyClass="flush">
      <div v-for="n in list" :key="n.id" class="news-item" @click="detail = n">
        <div class="news-time">
          <div class="hm">{{ n.time.slice(11) }}</div>
          <div class="date">{{ n.time.slice(5, 10) }}</div>
        </div>
        <div class="news-main">
          <div class="news-title">
            <Badge :tone="sentimentTone[n.sentiment]">{{ n.sentiment }}</Badge>
            <span>{{ n.title }}</span>
          </div>
          <p class="news-summary">{{ n.summary }}</p>
          <div class="news-meta">
            <span>{{ n.source }}</span>
            <span>·</span>
            <span>{{ n.category }}</span>
            <span>·</span>
            <span>AI 情绪分析：{{ n.sentiment }}</span>
          </div>
        </div>
      </div>
      <div v-if="list.length === 0" style="padding: 50px; text-align: center; color: var(--text-3)">
        没有找到相关新闻
      </div>
    </Card>

    <Modal :open="!!detail" @close="detail = null" :width="620">
      <template #title>
        <span style="display: flex; gap: 8px; align-items: center">
          <Badge :tone="detail && sentimentTone[detail.sentiment]">{{ detail?.sentiment }}</Badge>
          新闻详情
        </span>
      </template>

      <div v-if="detail">
        <h2 style="font-size: 18px; line-height: 1.5; margin-bottom: 12px">{{ detail.title }}</h2>
        <div class="news-meta" style="margin-bottom: 16px">
          <span>{{ detail.source }}</span>
          <span>{{ detail.time }}</span>
          <span>{{ detail.category }}</span>
        </div>
        <p style="color: var(--text-2); line-height: 1.9; margin-bottom: 14px">{{ detail.summary }}</p>
        <p style="color: var(--text-2); line-height: 1.9; margin-bottom: 18px">{{ detail.content }}</p>
        <div style="padding: 14px; border-radius: 10px; background: var(--bg-2); border: 1px solid var(--border)">
          <div style="font-size: 12.5px; color: var(--text-3); margin-bottom: 8px">AI 智能解读</div>
          <div style="font-size: 13px; line-height: 1.8">
            该消息被判定为
            <Badge :tone="sentimentTone[detail.sentiment]" style="margin: 0 6px">{{ detail.sentiment }}</Badge>
            ，对<span style="color: var(--accent-2); margin: 0 4px">{{ detail.category }}</span>
            板块短期情绪有正向催化，建议结合持仓与量化策略信号综合判断。
          </div>
        </div>
      </div>
    </Modal>
  </div>
</template>