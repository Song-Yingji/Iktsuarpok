<script setup>
import { onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { fmt, tone } from '../lib/utils'
import { Card, Button, Badge, Steps } from './ui'
import Icon from './Icon.vue'
import { useRecommendAgent } from '../store/agent'

const router = useRouter()

// 荐股结果与偏好选择托管在 store，组件卸载不销毁，切回本页自动恢复
const {
  REC_STEPS,
  recs,
  recText,
  recRunning: running,
  recStep: step,
  watchedCodes,
  prefSets,
  prefId,
  loadRecoDeps,
  runRecommend: run,
  stopRecommend: stop,
  addWatch
} = useRecommendAgent()

onMounted(loadRecoDeps)

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
        <Badge tone="info">Recommend Buffett v2.4</Badge>
      </span>
    </template>
    <template #extra>
      <Button v-if="running" size="sm" variant="ghost" @click="stop">停止</Button>
      <Button v-else size="sm" icon="bolt" @click="run">{{ recs ? '重新分析' : '开始智能选股' }}</Button>
    </template>

    <div class="rec-pref-bar">
      <div class="rec-pref-left">
        <Icon name="prefs" :size="15" />
        <span class="rec-pref-label">使用偏好</span>
        <select v-model="prefId" class="select rec-pref-select" :disabled="running">
          <option v-if="!prefSets.length" :value="null">未保存偏好（全市场）</option>
          <option v-for="p in prefSets" :key="p.id" :value="p.id">
            {{ p.name }}{{ p.isDefault ? '（默认）' : '' }}
          </option>
        </select>
      </div>
      <div class="rec-pref-right">
        <span class="rec-pref-hint">
          {{ prefSets.length ? '按所选偏好的关注板块筛选候选池' : '暂无已保存偏好，将扫描全市场' }}
        </span>
        <Button size="sm" variant="ghost" icon="prefs" @click="router.push('/preferences')">管理偏好</Button>
      </div>
    </div>

    <div v-if="running" class="rec-running">
      <Steps :steps="REC_STEPS" :current="step" />
      <div class="rec-running-text">
        <span class="rec-running-dot"></span>
        智能体正在{{ REC_STEPS[step] || '整理结果' }}，请稍候…
      </div>
    </div>

    <div v-if="recText" class="rec-analysis">
      <div class="rec-analysis-head">
        <Icon name="robot" :size="14" />
        AI 分析
      </div>
      <div class="rec-analysis-body">{{ recText }}<span v-if="running" class="cursor-blink">▍</span></div>
    </div>

    <div v-if="!running && !recs && !recText" class="rec-empty">
      <div class="rec-empty-icon">
        <Icon name="robot" :size="36" />
      </div>
      <div class="rec-empty-text">
        <strong>AI 智能选股</strong>
        <p>点击「开始智能选股」，AI 将基于你的投资偏好，从全市场扫描并输出综合评分最高的标的</p>
      </div>
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
        <div class="rec-foot">
          <Badge :tone="r.action === '建议买入' ? 'up' : 'warn'">{{ r.action }}</Badge>
          <span class="rec-meta">
            置信度 <b>{{ r.confidence }}%</b> · {{ r.sector }}
          </span>
        </div>
        <div class="rec-actions">
          <Button v-if="!watchedCodes.has(r.code)" size="sm" icon="plus" @click="addWatch(r)">加入自选</Button>
          <Button v-else size="sm" variant="ghost" disabled>已加入自选</Button>
        </div>
      </div>
    </div>
  </Card>
</template>

<style scoped>
.rec-pref-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  padding: 12px 14px;
  margin-bottom: 16px;
  background: var(--panel-2);
  border: 1px solid var(--border);
  border-radius: 10px;
}
.rec-pref-left { display: flex; align-items: center; gap: 8px; }
.rec-pref-right { display: flex; align-items: center; gap: 10px; }
.rec-pref-label { font-size: 13px; color: var(--text-2); font-weight: 500; }
.rec-pref-select { width: 200px !important; }
.rec-pref-hint { font-size: 11.5px; color: var(--text-3); }

.rec-running { padding: 22px 0 8px; }
.rec-running-text {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  color: var(--text-3);
  font-size: 12.5px;
}
.rec-running-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--accent-2);
  animation: pulse 1.6s infinite;
}

.rec-analysis {
  margin-bottom: 16px;
  padding: 14px 16px;
  background: rgba(14, 203, 129, 0.06);
  border: 1px solid rgba(14, 203, 129, 0.22);
  border-radius: 12px;
}
.rec-analysis-head {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  font-weight: 600;
  color: var(--accent-2);
  margin-bottom: 8px;
}
.rec-analysis-body {
  font-size: 13px;
  line-height: 1.75;
  color: var(--text-2);
  white-space: pre-wrap;
  max-height: 200px;
  overflow-y: auto;
}

.rec-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
  padding: 40px 20px;
  text-align: center;
}
.rec-empty-icon {
  width: 72px;
  height: 72px;
  border-radius: 20px;
  display: grid;
  place-items: center;
  background: linear-gradient(135deg, rgba(14, 203, 129, 0.1), rgba(56, 225, 255, 0.06));
  border: 1px solid rgba(14, 203, 129, 0.2);
  color: var(--accent-2);
}
.rec-empty-text strong { display: block; font-size: 16px; margin-bottom: 6px; }
.rec-empty-text p { color: var(--text-3); font-size: 13px; max-width: 380px; line-height: 1.6; }

.rec-card {
  border-radius: 12px;
  padding: 16px;
  background: linear-gradient(165deg, var(--bg-2), #0c1322);
  transition: all 0.2s;
}
.rec-card:hover {
  border-color: var(--accent);
  transform: translateY(-2px);
  box-shadow: 0 6px 20px rgba(0, 0, 0, 0.25);
}
.rec-foot {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 12px;
  padding-top: 10px;
  border-top: 1px solid rgba(32, 44, 71, 0.5);
}
.rec-meta { font-size: 11.5px; color: var(--text-3); }
.rec-meta b { color: var(--accent-2); }
.rec-actions { display: flex; justify-content: flex-end; margin-top: 10px; }

.cursor-blink {
  display: inline-block;
  margin-left: 2px;
  animation: blink 1s step-end infinite;
  color: var(--accent);
}
@keyframes blink {
  50% { opacity: 0; }
}
</style>
