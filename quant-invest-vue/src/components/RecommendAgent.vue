<script setup>
import { ref, onMounted } from 'vue'
import { agentApi, prefsApi, watchlistApi } from '../api'
import { fmt, tone } from '../lib/utils'
import { Card, Button, Badge, Steps } from './ui'
import Icon from './Icon.vue'
import { useApp } from '../store/app'

const REC_STEPS = ['扫描全市场', '技术面分析', '基本面筛选', 'AI 综合评分']

const { toast } = useApp()
const running = ref(false)
const step = ref(-1)
const recs = ref(null)
const watchedCodes = ref(new Set())
let prefs = null

onMounted(() => {
  prefsApi.get().then((p) => (prefs = p))
  watchlistApi.list().then((list) => (watchedCodes.value = new Set(list.map((s) => s.code)))).catch(() => {})
})

async function addWatch(r) {
  await watchlistApi.add(r.code)
  watchedCodes.value = new Set([...watchedCodes.value, r.code])
  toast(`已将 ${r.name} 加入自选股`)
}

async function run() {
  running.value = true
  recs.value = null
  for (let i = 0; i < REC_STEPS.length; i++) {
    step.value = i
    await new Promise((r) => setTimeout(r, 550))
  }
  const data = await agentApi.recommend(prefs)
  recs.value = data
  step.value = -1
  running.value = false
  toast('荐股智能体已完成本轮分析')
}

const R = 22
const C = 2 * Math.PI * R
function ringColor(score) { return score >= 90 ? '#f6465d' : score >= 84 ? '#f0b90b' : '#0ecb81' }
function dashOffset(score) { return C * (1 - score / 100) }
</script>

<template>
  <Card>
    <template #title>
      <span style="display: flex; align-items: center; gap: 9px">
        <span class="agent-avatar teal" style="width: 34px; height: 34px; border-radius: 9px">
          <Icon name="chart" :size="17" />
        </span>
        自动荐股智能体
        <Badge tone="info">StockGPT v2.4</Badge>
      </span>
    </template>
    <template #extra>
      <Button v-if="!running" size="sm" icon="bolt" @click="run">{{ recs ? '重新分析' : '开始智能选股' }}</Button>
    </template>

    <p style="color: var(--text-2); font-size: 13px; margin-bottom: 14px">
      基于你的投资偏好，融合技术指标、资金流向、基本面因子与舆情情绪，从全市场扫描并输出综合评分最高的标的。
    </p>

    <div v-if="running" style="padding: 26px 0">
      <Steps :steps="REC_STEPS" :current="step" />
      <div style="text-align: center; color: var(--text-3); font-size: 12.5px">
        智能体正在分析 {{ REC_STEPS[step] }}，请稍候…
      </div>
    </div>

    <div v-if="!running && !recs" class="empty-state" style="padding: 36px 20px">
      <Icon name="robot" :size="32" />
      <p>点击「开始智能选股」，AI 将为你扫描全市场机会</p>
    </div>

    <div v-if="recs" class="grid grid-3" style="gap: 12px">
      <div v-for="r in recs" :key="r.code" class="rec-card">
        <div class="rec-head">
          <div>
            <div style="font-weight: 700; font-size: 14.5px">
              {{ r.name }} <span style="color: var(--text-3); font-weight: 400; font-size: 12px">{{ r.code }}</span>
            </div>
            <div style="margin-top: 4px">
              <span :class="tone(r.change)" style="font-weight: 700; font-size: 15px">{{ fmt.price(r.price) }}</span>
              <span :class="tone(r.change)" style="font-size: 12px; margin-left: 8px">{{ fmt.pct(r.change) }}</span>
            </div>
          </div>
          <svg width="52" height="52" viewBox="0 0 52 52">
            <circle cx="26" cy="26" :r="R" fill="none" stroke="#26334f" stroke-width="4" />
            <circle
              cx="26" cy="26" :r="R" fill="none" :stroke="ringColor(r.score)" stroke-width="4"
              stroke-linecap="round" :stroke-dasharray="C" :stroke-dashoffset="dashOffset(r.score)"
              transform="rotate(-90 26 26)"
            />
            <text x="26" y="31" text-anchor="middle" font-size="15" font-weight="700" :fill="ringColor(r.score)">{{ r.score }}</text>
          </svg>
        </div>
        <ul class="rec-reasons">
          <li v-for="(rs, i) in r.reasons" :key="i">{{ rs }}</li>
        </ul>
        <div style="display: flex; justify-content: space-between; align-items: center; margin-top: 12px">
          <Badge :tone="r.action === '建议买入' ? 'up' : 'warn'">{{ r.action }}</Badge>
          <span style="font-size: 11.5px; color: var(--text-3)">
            置信度 <b style="color: var(--accent-2)">{{ r.confidence }}%</b> · {{ r.sector }}
          </span>
        </div>
        <div style="display: flex; justify-content: flex-end; margin-top: 10px">
          <Button v-if="!watchedCodes.has(r.code)" size="sm" icon="plus" @click="addWatch(r)">加入自选</Button>
          <Button v-else size="sm" variant="ghost" disabled>已加入自选</Button>
        </div>
      </div>
    </div>
  </Card>
</template>