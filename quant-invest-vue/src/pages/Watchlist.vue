<script setup>
import { ref, computed, onMounted } from 'vue'
import { watchlistApi } from '../api'
import { useApp } from '../store/app'
import { fmt, tone } from '../lib/utils'
import { Card, Badge } from '../components/ui'
import Icon from '../components/Icon.vue'

const { toast, market, marketError } = useApp()
const codes = ref([])
const loading = ref(true)

onMounted(async () => {
  try {
    const list = await watchlistApi.list()
    codes.value = list.map((s) => s.code)
  } finally {
    loading.value = false
  }
})

const stocks = computed(() => market.value.stocks.filter((s) => codes.value.includes(s.code)))
const chgOf = (p, prev) => (p - prev) / prev

async function remove(code) {
  try {
    await watchlistApi.remove(code)
  } catch (e) {
    toast(e.message, 'error')
    return
  }
  codes.value = codes.value.filter((c) => c !== code)
  toast('已从自选股移除')
}
</script>

<template>
  <div>
    <div class="page-head">
      <div>
        <h1>自选股</h1>
        <p>你关注的个股，实时行情每 2 秒更新</p>
      </div>
      <div class="page-actions">
        <Badge tone="info">{{ codes.length }} 只</Badge>
      </div>
    </div>

    <div v-if="marketError" style="display:flex;align-items:center;gap:8px;padding:10px 14px;margin-bottom:16px;background:rgba(246,70,93,0.12);border:1px solid rgba(246,70,93,0.35);border-radius:8px;color:#f6465d;font-size:13px;font-weight:500">
      <Icon name="close" :size="15" />
      <span>{{ marketError }}</span>
    </div>

    <Card title="自选股列表" bodyClass="flush">
      <div v-if="loading" style="text-align:center;padding:40px;color:var(--text-3)">自选股加载中…</div>
      <div v-else-if="!stocks.length" class="empty-state" style="padding: 48px 20px">
        <Icon name="star" :size="32" />
        <p>暂无自选股，可在「AI 智能体」荐股结果中一键加入，或到「行情中心」点击「加自选」</p>
      </div>
      <div v-else style="overflow-x: auto">
        <table class="data-table">
          <thead>
            <tr>
              <th>名称 / 代码</th>
              <th class="num">最新价</th>
              <th class="num">涨跌幅</th>
              <th class="num">涨跌额</th>
              <th class="num">成交量</th>
              <th class="num">成交额</th>
              <th>行业</th>
              <th style="text-align:center">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="s in stocks" :key="s.code">
              <td>
                <span class="stock-name">{{ s.name }}</span>
                <span class="stock-code">{{ s.code }}</span>
              </td>
              <td :class="['num', tone(chgOf(s.price, s.prevClose))]" style="font-weight: 600">{{ fmt.price(s.price) }}</td>
              <td :class="['num', tone(chgOf(s.price, s.prevClose))]" style="font-weight: 600">{{ fmt.pct(chgOf(s.price, s.prevClose)) }}</td>
              <td :class="['num', tone(chgOf(s.price, s.prevClose))]">{{ fmt.num(s.price - s.prevClose) }}</td>
              <td class="num">{{ fmt.vol(s.volume) }}</td>
              <td class="num">{{ fmt.vol(s.amount) }}</td>
              <td><Badge tone="neutral">{{ s.sector }}</Badge></td>
              <td style="text-align:center">
                <button type="button" class="icon-btn" title="移除自选" @click="remove(s.code)">
                  <Icon name="close" :size="15" />
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </Card>
  </div>
</template>