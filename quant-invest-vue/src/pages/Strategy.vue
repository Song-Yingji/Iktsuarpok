<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { runBacktest, strategyApi } from '../api'
import { fmt, tone } from '../lib/utils'
import { Card, Button, Badge, Field, Steps } from '../components/ui'
import EChart from '../components/EChart.vue'
import Icon from '../components/Icon.vue'
import { useApp } from '../store/app'

const RUN_STEPS = ['初始化回测框架', '加载历史行情', '逐K线模拟交易', '计算绩效指标']
const RANGES = [
  { label: '近 3 个月', value: 60 },
  { label: '近 6 个月', value: 120 },
  { label: '近 1 年', value: 240 }
]

function priceChartOption(result) {
  const { candles, points } = result
  const dates = candles.map((c) => c.date)
  const closes = candles.map((c) => +c.close.toFixed(2))
  return {
    animation: false,
    tooltip: { trigger: 'axis', backgroundColor: '#172136', borderColor: '#2a3a5c', textStyle: { color: '#e8eef9' } },
    grid: { left: 60, right: 20, top: 30, bottom: 54 },
    xAxis: { type: 'category', data: dates, axisLine: { lineStyle: { color: '#2a3a5c' } }, axisLabel: { color: '#62718f' } },
    yAxis: { scale: true, splitLine: { lineStyle: { color: 'rgba(42,58,92,0.3)' } }, axisLabel: { color: '#62718f' } },
    dataZoom: [{ type: 'inside', start: 0 }, { type: 'slider', bottom: 8, height: 16, borderColor: '#2a3a5c', fillerColor: 'rgba(76,141,255,0.15)', textStyle: { color: '#62718f' } }],
    series: [{
      name: '收盘价', type: 'line', data: closes, showSymbol: false, smooth: true,
      lineStyle: { width: 1.8, color: '#4c8dff' },
      areaStyle: {
        color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [
          { offset: 0, color: 'rgba(76,141,255,0.22)' }, { offset: 1, color: 'rgba(76,141,255,0)' }
        ] }
      },
      markPoint: {
        symbol: 'pin', symbolSize: 42,
        label: { color: '#fff', fontWeight: 700, fontSize: 11 },
        data: points.map((p) => ({
          coord: [p.date, +p.price.toFixed(2)],
          value: p.type === 'buy' ? 'B' : 'S',
          itemStyle: { color: p.type === 'buy' ? '#f6465d' : '#0ecb81' }
        }))
      }
    }]
  }
}

function equityChartOption(result) {
  const { equity, capital } = result
  return {
    animation: false,
    tooltip: { trigger: 'axis', backgroundColor: '#172136', borderColor: '#2a3a5c', textStyle: { color: '#e8eef9' }, valueFormatter: (v) => (v * 100).toFixed(1) + '%' },
    legend: { data: ['策略净值', '基准(买入持有)'], textStyle: { color: '#93a1bd' }, top: 0 },
    grid: { left: 60, right: 20, top: 34, bottom: 30 },
    xAxis: { type: 'category', data: equity.map((e) => e.date), axisLine: { lineStyle: { color: '#2a3a5c' } }, axisLabel: { color: '#62718f' } },
    yAxis: { scale: true, splitLine: { lineStyle: { color: 'rgba(42,58,92,0.3)' } }, axisLabel: { color: '#62718f', formatter: (v) => (v * 100).toFixed(0) + '%' } },
    series: [
      {
        name: '策略净值', type: 'line', showSymbol: false, smooth: true,
        data: equity.map((e) => +(e.value / capital).toFixed(4)),
        lineStyle: { width: 2, color: '#f0b90b' },
        areaStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [
          { offset: 0, color: 'rgba(240,185,11,0.2)' }, { offset: 1, color: 'rgba(240,185,11,0)' }
        ] } }
      },
      {
        name: '基准(买入持有)', type: 'line', showSymbol: false, smooth: true,
        data: equity.map((e) => +(e.bench / capital).toFixed(4)),
        lineStyle: { width: 1.4, color: '#62718f', type: 'dashed' }
      }
    ]
  }
}

function drawdownChartOption(result) {
  const { equity } = result
  let peak = -Infinity
  const dd = equity.map((e) => {
    peak = Math.max(peak, e.value)
    return +(((e.value / peak) - 1) * 100).toFixed(2)
  })
  return {
    animation: false,
    tooltip: { trigger: 'axis', backgroundColor: '#172136', borderColor: '#2a3a5c', textStyle: { color: '#e8eef9' }, valueFormatter: (v) => v + '%' },
    grid: { left: 60, right: 20, top: 20, bottom: 30 },
    xAxis: { type: 'category', data: equity.map((e) => e.date), axisLine: { lineStyle: { color: '#2a3a5c' } }, axisLabel: { color: '#62718f' } },
    yAxis: { splitLine: { lineStyle: { color: 'rgba(42,58,92,0.3)' } }, axisLabel: { color: '#62718f', formatter: '{value}%' } },
    series: [{
      type: 'line', data: dd, showSymbol: false, lineStyle: { width: 1.4, color: '#0ecb81' },
      areaStyle: { color: 'rgba(14,203,129,0.18)' }
    }]
  }
}

const { toast, market, frameworks } = useApp()
const router = useRouter()
const route = useRoute()
const stocks = computed(() => market.value.stocks)

const saved = ref([])
const loading = ref(true)
const selectedId = ref(null)
const stockCode = ref('600519')
const capital = ref(1000000)
const rangeDays = ref(120)
const framework = ref('quant')
const running = ref(false)
const step = ref(-1)
const result = ref(null)

const selected = computed(() => saved.value.find((s) => s.id === selectedId.value))
const frameworkName = computed(() => frameworks.value.find((f) => f.id === framework.value)?.name)

async function load() {
  loading.value = true
  try {
    saved.value = await strategyApi.saved()
    const focus = Number(route.query.focus)
    if (focus && saved.value.some((s) => s.id === focus)) selectedId.value = focus
    else if (!selectedId.value && saved.value.length) selectedId.value = saved.value[0].id
  } finally {
    loading.value = false
  }
}

function pickStrategy(id) {
  selectedId.value = id
  result.value = null
}

async function removeStrategy(s) {
  await strategyApi.remove(s.id)
  saved.value = saved.value.filter((x) => x.id !== s.id)
  if (selectedId.value === s.id) {
    selectedId.value = saved.value[0]?.id || null
    result.value = null
  }
  toast('策略已删除')
}

async function run() {
  if (!selected.value) return toast('请先选择一个量化策略', 'error')
  running.value = true
  result.value = null
  for (let i = 0; i < RUN_STEPS.length; i++) {
    step.value = i
    await new Promise((r) => setTimeout(r, 500))
  }
  const res = await runBacktest({
    strategyId: selected.value.engineId, stockCode: stockCode.value, params: selected.value.params,
    capital: capital.value, framework: framework.value, rangeDays: rangeDays.value
  })
  result.value = res
  step.value = -1
  running.value = false
  toast(`回测完成：累计收益 ${fmt.pct(res.metrics.totalReturn)}，共 ${res.metrics.tradeCount} 笔交易`)
}

const metrics = computed(() => result.value?.metrics)

const metricTiles = computed(() => {
  if (!metrics.value) return []
  const m = metrics.value
  return [
    { label: '累计收益率', value: fmt.pct(m.totalReturn), tone: tone(m.totalReturn), desc: `基准 ${fmt.pct(m.benchReturn)}` },
    { label: '年化收益率', value: fmt.pct(m.annualized), tone: tone(m.annualized), desc: '按 252 个交易日折算' },
    { label: '最大回撤', value: fmt.pct(m.maxDD), tone: 'down', desc: '净值从峰值最大跌幅' },
    { label: '夏普比率', value: m.sharpe.toFixed(2), tone: m.sharpe >= 1 ? 'up' : '', desc: '无风险收益取 0' },
    { label: 'CVaR (95%)', value: fmt.pct(m.cvar), tone: 'down', desc: '最坏 5% 情况的平均日收益' },
    { label: '交易胜率', value: fmt.pctPlain(m.winRate, 1), tone: 'up', desc: `共 ${m.tradeCount} 笔交易` },
    { label: '盈亏比', value: m.plRatio.toFixed(2), tone: 'up', desc: '平均盈利 / 平均亏损' },
    { label: '期末资产', value: fmt.moneyWan(m.finalValue), tone: tone(m.totalReturn), desc: `初始 ${fmt.moneyWan(capital.value)}` }
  ]
})

onMounted(load)
</script>

<template>
  <div>
    <div class="page-head">
      <div>
        <h1>量化策略与回测</h1>
        <p>展示智能体生成或自由构建保存的策略，选择回测标的、区间和框架，用历史数据验证策略有效性</p>
      </div>
      <div class="page-actions">
        <Button icon="sliders" @click="router.push('/strategy/builder')">自由构建新策略</Button>
      </div>
    </div>

    <Card title="① 选择量化策略">
      <div v-if="loading" style="text-align:center;padding:32px;color:var(--text-3)">策略加载中…</div>
      <div v-else-if="!saved.length" class="empty-state" style="padding: 32px 20px">
        <Icon name="strategy" :size="30" />
        <p>暂无已保存的策略，可前往「AI 智能体」生成，或在「自由构建」页拖拽搭建</p>
      </div>
      <div v-else class="grid grid-3" style="gap: 12px">
        <div
          v-for="s in saved"
          :key="s.id"
          :class="['strat-card', selectedId === s.id && 'selected']"
          @click="pickStrategy(s.id)"
        >
          <div style="display: flex; justify-content: space-between; align-items: flex-start; gap: 8px">
            <h4 style="margin-bottom: 6px">
              {{ s.name }}
              <Badge tone="neutral">{{ s.type }}</Badge>
            </h4>
            <div style="display: flex; gap: 2px; flex-shrink: 0">
              <button
                v-if="s.engineId === 'builder'"
                class="icon-btn"
                title="编辑策略"
                @click.stop="router.push(`/strategy/builder/${s.id}`)"
              >
                <Icon name="sliders" :size="15" />
              </button>
              <button class="icon-btn" title="删除策略" @click.stop="removeStrategy(s)">
                <Icon name="close" :size="15" />
              </button>
            </div>
          </div>
          <p>{{ (s.rules && s.rules[0]) || '无策略规则描述' }}</p>
          <div class="strat-meta">
            <Badge :tone="s.engineId === 'builder' ? 'purple' : 'info'">
              {{ s.engineId === 'builder' ? '自由构建' : '智能体生成' }}
            </Badge>
            <Badge tone="neutral">{{ s.createdAt }}</Badge>
          </div>
        </div>
      </div>
    </Card>

    <div class="grid mt-16" style="gap: 12px">
      <Card title="② 回测设置（标的 · 区间 · 框架）">
        <div class="grid grid-2" style="gap: 20px 24px">
          <Field label="回测标的">
            <select class="select" v-model="stockCode">
              <option v-for="s in stocks" :key="s.code" :value="s.code">{{ s.name }}（{{ s.code }}）</option>
            </select>
          </Field>
          <Field label="回测区间">
            <div class="segmented" style="display: flex">
              <button
                v-for="r in RANGES"
                :key="r.value"
                type="button"
                :class="['seg-item', rangeDays === r.value && 'active']"
                style="flex: 1"
                @click="rangeDays = r.value"
              >
                {{ r.label }}
              </button>
            </div>
          </Field>
        </div>
        <Field label="回测框架">
          <div class="grid grid-2" style="gap: 10px">
            <div
              v-for="f in frameworks"
              :key="f.id"
              :class="['fw-card', framework === f.id && 'selected']"
              @click="framework = f.id"
            >
              <h4>
                {{ f.name }}
                <Badge v-if="f.tag" tone="up">{{ f.tag }}</Badge>
              </h4>
              <p>{{ f.desc }}</p>
            </div>
          </div>
        </Field>
      </Card>
    </div>

    <Card class="mt-16" title="③ 回测分析">
      <template #extra>
        <Button icon="bolt" :loading="running" :disabled="!selected" @click="run">
          {{ running ? '回测进行中…' : '运行回测' }}
        </Button>
      </template>
      <div v-if="running">
        <Steps :steps="RUN_STEPS" :current="step" />
        <div style="text-align: center; color: var(--text-3); font-size: 12.5px; margin-top: 8px">
          正在使用 {{ frameworkName }} 执行回测，逐K线模拟 {{ rangeDays }} 个交易日…
        </div>
      </div>
      <div v-else-if="!result" class="empty-state" style="padding: 24px 20px">
        <Icon name="chart" :size="28" />
        <p>点击「运行回测」，这里将展示买卖点、资金曲线与绩效评价</p>
      </div>
    </Card>

    <template v-if="result">
      <Card class="mt-16">
        <template #title>
          <span style="display: flex; gap: 10px; align-items: center">
            回测绩效评价
            <Badge tone="info">{{ frameworkName }}</Badge>
            <Badge tone="neutral">{{ result.stock.name }} · {{ rangeDays }} 个交易日</Badge>
          </span>
        </template>
        <div class="grid" style="grid-template-columns: repeat(4, 1fr); gap: 12px">
          <div v-for="m in metricTiles" :key="m.label" class="metric-tile">
            <div class="m-label">{{ m.label }}</div>
            <div :class="['m-value', m.tone]">{{ m.value }}</div>
            <div class="m-desc">{{ m.desc }}</div>
          </div>
        </div>
      </Card>

      <div class="grid grid-2 mt-16">
        <Card title="价格走势与买卖点标记（B 买入 / S 卖出）" bodyClass="flush">
          <EChart :option="priceChartOption(result)" style="height: 340px" />
        </Card>
        <Card title="策略累计收益率 vs 基准" bodyClass="flush">
          <EChart :option="equityChartOption(result)" style="height: 340px" />
        </Card>
      </div>

      <Card class="mt-16" title="回撤曲线（Drawdown）" bodyClass="flush">
        <EChart :option="drawdownChartOption(result)" style="height: 220px" />
      </Card>

      <Card class="mt-16" :title="`交易明细（${result.trades.length} 笔）`" bodyClass="flush">
        <div style="overflow-x: auto">
          <table class="data-table">
            <thead>
              <tr>
                <th>#</th><th>买入日期</th><th class="num">买入价</th>
                <th>卖出日期</th><th class="num">卖出价</th>
                <th class="num">持仓天数</th><th class="num">收益率</th><th>备注</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(t, i) in result.trades" :key="i">
                <td>{{ i + 1 }}</td>
                <td>{{ t.entryDate }}</td>
                <td class="num">{{ fmt.price(t.entryPrice) }}</td>
                <td>{{ t.exitDate }}</td>
                <td class="num">{{ fmt.price(t.exitPrice) }}</td>
                <td class="num">{{ t.days }} 天</td>
                <td :class="['num', tone(t.ret)]" style="font-weight: 600">{{ fmt.pct(t.ret) }}</td>
                <td>{{ t.stopped ? '触发止损' : '信号平仓' }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </Card>
    </template>
  </div>
</template>