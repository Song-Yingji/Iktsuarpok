<script setup>
import { ref, computed, onMounted } from 'vue'
import { positionApi } from '../api'
import { fmt, tone } from '../lib/utils'
import { Card, StatCard, Badge, Drawer, Button } from '../components/ui'
import EChart from '../components/EChart.vue'
import { useApp } from '../store/app'

const { market } = useApp()

const data = ref(null)
const loading = ref(false)
const selected = ref(null)

const summary = computed(() => data.value?.summary)
const positions = computed(() => data.value?.positions || [])
const accounts = computed(() => data.value?.accounts || [])

function sectorOf(code) {
  const s = market.value.stocks.find((x) => x.code === code)
  return s ? s.sector : '其他'
}

// 持仓市值分布
const pieOption = computed(() => {
  const list = positions.value.map((p) => ({ name: p.name, value: Math.round(p.marketValue) }))
  return buildPieOption(list, false)
})

// 行业分布
const sectorOption = computed(() => {
  const map = {}
  positions.value.forEach((p) => {
    const sec = sectorOf(p.code)
    map[sec] = (map[sec] || 0) + p.marketValue
  })
  const list = Object.entries(map).map(([name, value]) => ({ name, value: Math.round(value) }))
  return buildPieOption(list, true)
})

function buildPieOption(list, verticalLegend) {
  return {
    animation: false,
    tooltip: {
      trigger: 'item', backgroundColor: '#172136', borderColor: '#2a3a5c', textStyle: { color: '#e8eef9' },
      formatter: (p) => `${p.name}<br/>${fmt.money(p.value)}（${p.percent}%）`
    },
    legend: verticalLegend
      ? { orient: 'vertical', right: 10, top: 'middle', textStyle: { color: '#93a1bd', fontSize: 11 }, itemHeight: 9 }
      : { bottom: 0, textStyle: { color: '#93a1bd', fontSize: 11 }, itemHeight: 9 },
    series: [{
      type: 'pie',
      radius: verticalLegend ? ['40%', '68%'] : ['45%', '72%'],
      center: verticalLegend ? ['38%', '50%'] : ['50%', '44%'],
      itemStyle: { borderColor: '#0a0e17', borderWidth: 2, borderRadius: 4 },
      label: { show: false },
      emphasis: { label: { show: true, fontWeight: 700, color: '#e8eef9', formatter: '{b}\n{d}%' } },
      data: list
    }]
  }
}

// 各账户净值曲线
const equityOption = computed(() => {
  const list = accounts.value.filter((a) => a.curve?.length)
  if (!list.length) return null
  return {
    animation: false,
    tooltip: { trigger: 'axis', backgroundColor: '#172136', borderColor: '#2a3a5c', textStyle: { color: '#e8eef9' }, valueFormatter: (v) => fmt.money(v) },
    legend: { data: list.map((a) => a.broker), textStyle: { color: '#93a1bd' }, top: 0 },
    grid: { left: 70, right: 20, top: 34, bottom: 30 },
    xAxis: { type: 'category', data: list[0].curve.map((c) => c.date), axisLine: { lineStyle: { color: '#2a3a5c' } }, axisLabel: { color: '#62718f' } },
    yAxis: { type: 'value', splitLine: { lineStyle: { color: 'rgba(42,58,92,0.3)' } }, axisLabel: { color: '#62718f', formatter: (v) => fmt.moneyWan(v) } },
    series: list.map((a) => ({
      name: a.broker, type: 'line', showSymbol: false, smooth: true,
      data: a.curve.map((c) => c.value), lineStyle: { width: 2 }
    }))
  }
})

// 投资分析指标
const winCount = computed(() => positions.value.filter((p) => p.pnl > 0).length)
const lossCount = computed(() => positions.value.filter((p) => p.pnl <= 0).length)
const maxWeight = computed(() => (positions.value.length ? Math.max(...positions.value.map((p) => p.weight)) : 0))
const avgPnlPct = computed(() => {
  if (!positions.value.length) return 0
  return positions.value.reduce((a, p) => a + p.pnlPct, 0) / positions.value.length
})

const analysisTiles = computed(() => [
  { label: '持仓股票数', value: positions.value.length + ' 只', desc: '当前开放仓位' },
  { label: '盈利 / 亏损', value: `${winCount.value} / ${lossCount.value}`, desc: '按浮动盈亏划分', tone: winCount.value >= lossCount.value ? 'up' : 'down' },
  { label: '最大单票仓位', value: fmt.pctPlain(maxWeight.value), desc: '集中度风险提示', tone: maxWeight.value > 0.3 ? 'down' : '' },
  { label: '平均盈亏率', value: fmt.pct(avgPnlPct.value), desc: '全部持仓算术平均', tone: tone(avgPnlPct.value) }
])

async function load() {
  loading.value = true
  data.value = await positionApi.get()
  loading.value = false
}

onMounted(load)
</script>

<template>
  <div>
    <div class="page-head">
      <div>
        <h1>资产与仓位</h1>
        <p>实时查看账户资产、持仓明细与投资情况分析</p>
      </div>
      <div class="page-actions">
        <Button variant="ghost" :loading="loading" @click="load">刷新</Button>
      </div>
    </div>

    <!-- 资产概览 -->
    <div v-if="summary" class="grid grid-5">
      <StatCard icon="wallet" label="总资产" :value="fmt.money(summary.totalAssets)" sub="现金 + 持仓市值" />
      <StatCard icon="chart" label="持仓市值" :value="fmt.money(summary.totalMarketValue)" sub="当前持有股票市值" />
      <StatCard icon="check" label="可用资金" :value="fmt.money(summary.cash)" sub="可立即调用的现金" />
      <StatCard icon="up" label="浮动盈亏" :value="fmt.money(summary.totalPnl)" :tone="tone(summary.totalPnl)" :sub="`成本 ${fmt.money(summary.totalCost)}`" />
      <StatCard icon="bolt" label="当日盈亏" :value="fmt.money(summary.dayPnl)" :tone="tone(summary.dayPnl)" sub="按最新行情估算" />
    </div>

    <!-- 净值与分布 -->
    <div class="grid grid-2 mt-16">
      <Card title="资产净值走势" bodyClass="flush">
        <EChart v-if="equityOption" :option="equityOption" style="height: 300px" />
      </Card>
      <Card title="持仓市值分布" bodyClass="flush">
        <EChart :option="pieOption" style="height: 300px" />
      </Card>
    </div>

    <!-- 行业分布与投资分析 -->
    <div class="grid grid-2 mt-16">
      <Card title="行业分布" bodyClass="flush">
        <EChart :option="sectorOption" style="height: 240px" />
      </Card>
      <Card title="投资情况分析">
        <div class="grid" style="grid-template-columns: 1fr 1fr; gap: 12px">
          <div v-for="t in analysisTiles" :key="t.label" class="metric-tile">
            <div class="m-label">{{ t.label }}</div>
            <div :class="['m-value', t.tone]">{{ t.value }}</div>
            <div class="m-desc">{{ t.desc }}</div>
          </div>
        </div>
      </Card>
    </div>

    <!-- 持仓明细 -->
    <Card class="mt-16" :title="`持仓明细（${positions.length} 只）`" bodyClass="flush">
      <div style="overflow-x: auto">
        <table class="data-table table-clickable">
          <thead>
            <tr>
              <th>股票</th>
              <th>行业</th>
              <th class="num">持仓数量</th>
              <th class="num">成本价</th>
              <th class="num">现价</th>
              <th class="num">市值</th>
              <th class="num">浮动盈亏</th>
              <th class="num">盈亏比例</th>
              <th class="num">仓位占比</th>
              <th class="num">当日涨跌</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="p in positions" :key="p.code" @click="selected = p">
              <td><span class="stock-name">{{ p.name }}</span><span class="stock-code">{{ p.code }}</span></td>
              <td>{{ sectorOf(p.code) }}</td>
              <td class="num">{{ fmt.num(p.qty, 0) }}</td>
              <td class="num">{{ fmt.price(p.cost) }}</td>
              <td class="num">{{ fmt.price(p.price) }}</td>
              <td class="num">{{ fmt.money(p.marketValue) }}</td>
              <td class="num" :class="tone(p.pnl)" style="font-weight:600">{{ fmt.money(p.pnl) }}</td>
              <td class="num" :class="tone(p.pnlPct)" style="font-weight:600">{{ fmt.pct(p.pnlPct) }}</td>
              <td class="num">{{ fmt.pctPlain(p.weight) }}</td>
              <td class="num" :class="tone(p.dayPct)">{{ fmt.pct(p.dayPct) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </Card>

    <!-- 持仓详情抽屉 -->
    <Drawer :open="!!selected" title="持仓详情" :width="420" @close="selected = null">
      <template v-if="selected">
        <div style="display:flex;align-items:center;gap:12px;margin-bottom:18px">
          <span class="broker-icon" style="border-radius:12px">{{ selected.name.slice(0, 1) }}</span>
          <div>
            <strong style="font-size:16px">{{ selected.name }}</strong>
            <div style="font-size:12px;color:var(--text-3)">{{ selected.code }} · {{ sectorOf(selected.code) }}</div>
          </div>
          <Badge :tone="tone(selected.pnlPct)" style="margin-left:auto">{{ fmt.pct(selected.pnlPct) }}</Badge>
        </div>
        <div class="kv-list">
          <div class="kv-row"><span class="k">持仓数量</span><span>{{ fmt.num(selected.qty, 0) }} 股</span></div>
          <div class="kv-row"><span class="k">成本价</span><span>{{ fmt.price(selected.cost) }}</span></div>
          <div class="kv-row"><span class="k">现价</span><span>{{ fmt.price(selected.price) }}</span></div>
          <div class="kv-row"><span class="k">持仓市值</span><span>{{ fmt.money(selected.marketValue) }}</span></div>
          <div class="kv-row"><span class="k">浮动盈亏</span><span :class="tone(selected.pnl)">{{ fmt.money(selected.pnl) }}</span></div>
          <div class="kv-row"><span class="k">仓位占比</span><span>{{ fmt.pctPlain(selected.weight) }}</span></div>
          <div class="kv-row"><span class="k">当日涨跌</span><span :class="tone(selected.dayPct)">{{ fmt.pct(selected.dayPct) }}</span></div>
        </div>
      </template>
    </Drawer>
  </div>
</template>