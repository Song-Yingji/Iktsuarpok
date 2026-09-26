<script setup>
import { ref, computed, onMounted } from 'vue'
import { useApp } from '../store/app'
import { watchlistApi } from '../api'
import { fmt, tone } from '../lib/utils'
import { Card, Chip, Drawer, Button, Badge } from '../components/ui'
import EChart from '../components/EChart.vue'
import Icon from '../components/Icon.vue'

const { toast, market, marketError } = useApp()
const watched = ref(new Set())

onMounted(async () => {
  try {
    const list = await watchlistApi.list()
    watched.value = new Set(list.map((s) => s.code))
  } catch (e) {}
})

async function addWatch(s) {
  await watchlistApi.add(s.code)
  watched.value = new Set([...watched.value, s.code])
  toast(`已将 ${s.name} 加入自选股`)
}

// 迷你走势图
function sparkOption(data, up) {
  return {
    animation: false,
    grid: { left: 0, right: 0, top: 4, bottom: 0 },
    xAxis: { type: 'category', show: false, data: data.map((_, i) => i) },
    yAxis: { type: 'value', show: false, scale: true },
    tooltip: { show: false },
    series: [{
      type: 'line', data, showSymbol: false, smooth: true,
      lineStyle: { width: 1.5, color: up ? '#f6465d' : '#0ecb81' },
      areaStyle: {
        color: {
          type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
          colorStops: [
            { offset: 0, color: up ? 'rgba(246,70,93,0.25)' : 'rgba(14,203,129,0.25)' },
            { offset: 1, color: 'rgba(0,0,0,0)' }
          ]
        }
      }
    }]
  }
}

// K线图配置
function klineOption(stock) {
  const k = stock.history
  const dates = k.map((c) => c.date.slice(5))
  const ohlc = k.map((c) => [+c.open.toFixed(2), +c.close.toFixed(2), +c.low.toFixed(2), +c.high.toFixed(2)])
  const ma = (n) => {
    const out = []
    for (let i = 0; i < k.length; i++) {
      if (i < n - 1) { out.push(null); continue }
      let s = 0
      for (let j = i - n + 1; j <= i; j++) s += k[j].close
      out.push(+(s / n).toFixed(2))
    }
    return out
  }
  const vol = k.map((c) => ({
    value: c.volume,
    itemStyle: { color: c.close >= c.open ? 'rgba(246,70,93,0.6)' : 'rgba(14,203,129,0.6)' }
  }))
  return {
    animation: false,
    tooltip: { trigger: 'axis', axisPointer: { type: 'cross' }, backgroundColor: '#172136', borderColor: '#2a3a5c', textStyle: { color: '#e8eef9' } },
    legend: { data: ['K线', 'MA5', 'MA20', 'MA60'], textStyle: { color: '#93a1bd' }, top: 4 },
    axisPointer: { link: [{ xAxisIndex: 'all' }] },
    grid: [
      { left: 56, right: 16, top: 38, height: '56%' },
      { left: 56, right: 16, top: '74%', height: '16%' }
    ],
    xAxis: [
      { type: 'category', data: dates, scale: true, boundaryGap: false, axisLine: { lineStyle: { color: '#2a3a5c' } }, axisLabel: { color: '#62718f' }, splitLine: { show: false } },
      { type: 'category', gridIndex: 1, data: dates, scale: true, boundaryGap: false, axisLine: { lineStyle: { color: '#2a3a5c' } }, axisLabel: { show: false }, splitLine: { show: false } }
    ],
    yAxis: [
      { scale: true, splitLine: { lineStyle: { color: 'rgba(42,58,92,0.3)' } }, axisLabel: { color: '#62718f' } },
      { gridIndex: 1, scale: true, splitLine: { show: false }, axisLabel: { color: '#62718f', formatter: (v) => fmt.vol(v) } }
    ],
    dataZoom: [
      { type: 'inside', xAxisIndex: [0, 1], start: 55 },
      { type: 'slider', xAxisIndex: [0, 1], bottom: 6, height: 16, borderColor: '#2a3a5c', fillerColor: 'rgba(76,141,255,0.15)', textStyle: { color: '#62718f' } }
    ],
    series: [
      {
        name: 'K线', type: 'candlestick', data: ohlc,
        itemStyle: { color: '#f6465d', color0: '#0ecb81', borderColor: '#f6465d', borderColor0: '#0ecb81' }
      },
      { name: 'MA5', type: 'line', data: ma(5), smooth: true, showSymbol: false, lineStyle: { width: 1.2, color: '#f0b90b' } },
      { name: 'MA20', type: 'line', data: ma(20), smooth: true, showSymbol: false, lineStyle: { width: 1.2, color: '#a66bff' } },
      { name: 'MA60', type: 'line', data: ma(60), smooth: true, showSymbol: false, lineStyle: { width: 1.2, color: '#38e1ff' } },
      { name: '成交量', type: 'bar', xAxisIndex: 1, yAxisIndex: 1, data: vol }
    ]
  }
}

const keyword = ref('')
const sector = ref('全部')
const selected = ref(null)

const sectors = computed(() => ['全部', ...Array.from(new Set(market.value.stocks.map((s) => s.sector)))])

const filtered = computed(() => market.value.stocks.filter((s) => {
  const kw = keyword.value.trim()
  const matchKw = !kw || s.name.includes(kw) || s.code.includes(kw)
  const matchSec = sector.value === '全部' || s.sector === sector.value
  return matchKw && matchSec
}))

const chgOf = (p, prev) => (p - prev) / prev
</script>

<template>
  <div>
    <div class="page-head">
      <div>
        <h1>行情中心</h1>
        <p>A股大盘指数与个股实时行情 · 数据每 2 秒推送</p>
      </div>
      <div class="page-actions">
        <Badge tone="info" dot>交易中 09:30 - 15:00</Badge>
      </div>
    </div>

    <!-- 行情异常提示 -->
    <div v-if="marketError" style="display:flex;align-items:center;gap:8px;padding:10px 14px;margin-bottom:16px;background:rgba(246,70,93,0.12);border:1px solid rgba(246,70,93,0.35);border-radius:8px;color:#f6465d;font-size:13px;font-weight:500">
      <Icon name="close" :size="15" />
      <span>{{ marketError }}</span>
    </div>

    <!-- 大盘指数 -->
    <div class="grid grid-4">
      <div v-for="ix in market.indices" :key="ix.code" class="index-card">
        <div class="index-name">
          <span>{{ ix.name }}</span>
          <span style="font-size: 11px">{{ ix.code }}</span>
        </div>
        <div :class="['index-price', tone(chgOf(ix.price, ix.prevClose))]">{{ fmt.price(ix.price) }}</div>
        <div :class="['index-chg', tone(chgOf(ix.price, ix.prevClose))]">
          {{ fmt.pct(chgOf(ix.price, ix.prevClose)) }} &nbsp;{{ fmt.num(ix.price - ix.prevClose) }}
        </div>
        <EChart :option="sparkOption(ix.spark, chgOf(ix.price, ix.prevClose) >= 0)" style="height: 34px; margin-top: 6px" />
      </div>
    </div>

    <!-- 个股列表 -->
    <Card class="mt-16" title="个股行情" bodyClass="flush">
      <template #extra>
        <div class="search-box" style="width: 220px">
          <Icon name="search" :size="15" />
          <input class="input" placeholder="搜索股票代码 / 名称" v-model="keyword" />
        </div>
      </template>

      <div style="padding: 12px 16px 0; display: flex; gap: 8px; flex-wrap: wrap">
        <Chip v-for="s in sectors" :key="s" :active="sector === s" @click="sector = s">{{ s }}</Chip>
      </div>
      <div style="overflow-x: auto; margin-top: 8px">
        <table class="data-table table-clickable">
          <thead>
            <tr>
              <th>名称 / 代码</th>
              <th class="num">最新价</th>
              <th class="num">涨跌幅</th>
              <th class="num">涨跌额</th>
              <th class="num">成交量</th>
              <th class="num">成交额</th>
              <th class="num">换手率</th>
              <th class="num">市盈率(动)</th>
              <th>行业</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="s in filtered" :key="s.code" @click="selected = s">
              <td>
                <span class="stock-name">{{ s.name }}</span>
                <span class="stock-code">{{ s.code }}</span>
              </td>
              <td :class="['num', tone(chgOf(s.price, s.prevClose)), s.price > s.lastPrice ? 'flash-up' : s.price < s.lastPrice ? 'flash-down' : '']" style="font-weight: 600">{{ fmt.price(s.price) }}</td>
              <td :class="['num', tone(chgOf(s.price, s.prevClose))]" style="font-weight: 600">{{ fmt.pct(chgOf(s.price, s.prevClose)) }}</td>
              <td :class="['num', tone(chgOf(s.price, s.prevClose))]">{{ fmt.num(s.price - s.prevClose) }}</td>
              <td class="num">{{ fmt.vol(s.volume) }}</td>
              <td class="num">{{ fmt.vol(s.amount) }}</td>
              <td class="num">{{ fmt.pctPlain(s.turnover / 100) }}</td>
              <td class="num">{{ fmt.num(s.pe, 1) }}</td>
              <td><Badge tone="neutral">{{ s.sector }}</Badge></td>
            </tr>
          </tbody>
        </table>
      </div>
    </Card>

    <!-- K线详情抽屉 -->
    <Drawer :open="!!selected" @close="selected = null" :width="760">
      <template #title>
        <span style="display: flex; align-items: center; gap: 12px">
          {{ selected?.name }} <span style="color: var(--text-3); font-size: 13px">{{ selected?.code }}</span>
          <Badge tone="neutral">{{ selected?.sector }}</Badge>
        </span>
      </template>

      <template v-if="selected">
        <div style="display: flex; align-items: baseline; gap: 16px; margin-bottom: 14px; flex-wrap: wrap">
          <span :class="tone(chgOf(selected.price, selected.prevClose))" style="font-size: 30px; font-weight: 700">
            {{ fmt.price(selected.price) }}
          </span>
          <span :class="tone(chgOf(selected.price, selected.prevClose))" style="font-size: 15px; font-weight: 600">
            {{ fmt.pct(chgOf(selected.price, selected.prevClose)) }}
            &nbsp;({{ fmt.num(selected.price - selected.prevClose) }})
          </span>
          <Button v-if="!watched.has(selected.code)" size="sm" icon="plus" @click="addWatch(selected)">加自选</Button>
          <Button v-else size="sm" variant="ghost" disabled>已加入自选</Button>
        </div>

        <div class="kv-list" style="margin-bottom: 16px">
          <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 6px">
            <div
              v-for="[k, v, c] in [
                ['今开', fmt.price(selected.open), tone(chgOf(selected.open, selected.prevClose))],
                ['昨收', fmt.price(selected.prevClose), ''],
                ['最高', fmt.price(selected.high), 'up'],
                ['最低', fmt.price(selected.low), 'down'],
                ['成交量', fmt.vol(selected.volume), ''],
                ['成交额', fmt.vol(selected.amount), ''],
                ['换手率', fmt.pctPlain(selected.turnover / 100), ''],
                ['市盈率', fmt.num(selected.pe, 1), '']
              ]"
              :key="k"
              style="padding: 8px 10px; background: var(--bg-2); border-radius: 8px"
            >
              <div style="font-size: 11px; color: var(--text-3)">{{ k }}</div>
              <div :class="c" style="font-weight: 600; font-size: 14px">{{ v }}</div>
            </div>
          </div>
        </div>

        <Card title="日K线 · MA均线 · 成交量" bodyClass="flush">
          <EChart v-if="selected.history && selected.history.length" :option="klineOption(selected)" style="height: 420px" />
          <div v-else style="height:420px;display:flex;align-items:center;justify-content:center;color:var(--text-3);font-size:13px">历史行情暂时不可用，请稍后重试</div>
        </Card>
      </template>
    </Drawer>
  </div>
</template>