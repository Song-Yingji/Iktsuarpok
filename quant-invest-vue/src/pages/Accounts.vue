<script setup>
import { ref, computed, onMounted } from 'vue'
import { accountApi } from '../api'
import { fmt } from '../lib/utils'
import { Card, StatCard, Button, Badge, Toggle, Modal, Field } from '../components/ui'
import { useApp } from '../store/app'

const { toast, strategies } = useApp()

const STATUS = {
  active: { label: '运行中', tone: 'up' },
  connected: { label: '已连接', tone: 'info' },
  disconnected: { label: '未连接', tone: 'neutral' }
}

const accounts = ref([])
const loading = ref(false)
const savingId = ref(null)

const showCreate = ref(false)
const creating = ref(false)
const form = ref({ broker: '', type: '模拟盘', capital: 100000, accountNo: '' })

const totalAssets = computed(() => accounts.value.reduce((a, x) => a + x.totalAssets, 0))
const totalCash = computed(() => accounts.value.reduce((a, x) => a + x.cash, 0))
const autoCount = computed(() => accounts.value.filter((x) => x.autoTrade).length)

async function load() {
  loading.value = true
  accounts.value = await accountApi.list()
  loading.value = false
}

async function patch(acc, changes) {
  savingId.value = acc.id
  try {
    const updated = await accountApi.update(acc.id, changes)
    const i = accounts.value.findIndex((x) => x.id === acc.id)
    if (i >= 0) accounts.value[i] = updated
    toast('账户已更新')
  } catch (e) {
    toast(e.message, 'error')
  } finally {
    savingId.value = null
  }
}

function onStrategy(acc, e) {
  const strategyId = e.target.value || null
  patch(acc, { strategyId })
}

function onAuto(acc, checked) {
  patch(acc, { autoTrade: checked })
}

async function createAccount() {
  if (!form.value.broker.trim()) return toast('请填写券商/账户名称', 'error')
  creating.value = true
  try {
    const acc = await accountApi.create({ ...form.value })
    accounts.value.push(acc)
    showCreate.value = false
    form.value = { broker: '', type: '模拟盘', capital: 100000, accountNo: '' }
    toast('账户创建成功')
  } finally {
    creating.value = false
  }
}

onMounted(load)
</script>

<template>
  <div>
    <div class="page-head">
      <div>
        <h1>账户管理</h1>
        <p>统一管理多个交易账户，为每个账户绑定量化策略并开关自动交易</p>
      </div>
      <div class="page-actions">
        <Button icon="plus" @click="showCreate = true">添加账户</Button>
      </div>
    </div>

    <!-- 概览 -->
    <div class="grid grid-4">
      <StatCard icon="wallet" label="账户总数" :value="accounts.length" sub="实时同步的账户数量" />
      <StatCard icon="account" label="总资产" :value="fmt.money(totalAssets)" sub="全部账户资产合计" />
      <StatCard icon="check" label="可用资金" :value="fmt.money(totalCash)" sub="可立即调用的现金" />
      <StatCard icon="bolt" label="自动交易" :value="autoCount" :sub="`${accounts.length} 个账户中已开启`" :tone="autoCount > 0 ? 'up' : ''" />
    </div>

    <!-- 账户卡列表 -->
    <div v-if="loading" style="text-align:center;padding:40px;color:var(--text-3)">账户加载中…</div>
    <div v-else class="grid grid-2 mt-16">
      <div v-for="acc in accounts" :key="acc.id" class="account-card">
        <div class="account-top">
          <div class="account-broker">
            <span class="broker-icon">{{ acc.broker.slice(0, 1) }}</span>
            <div>
              <strong>{{ acc.broker }}</strong>
              <small>{{ acc.type }} · {{ acc.accountNo }}</small>
            </div>
          </div>
          <Badge :tone="STATUS[acc.status]?.tone || 'neutral'" dot>{{ STATUS[acc.status]?.label || acc.status }}</Badge>
        </div>

        <div class="account-nums">
          <div class="account-num">
            <div class="n-label">总资产</div>
            <div class="n-value">{{ fmt.money(acc.totalAssets) }}</div>
          </div>
          <div class="account-num">
            <div class="n-label">可用资金</div>
            <div class="n-value">{{ fmt.money(acc.cash) }}</div>
          </div>
        </div>

        <div class="account-row">
          <span class="r-label">量化策略</span>
          <select
            class="select" style="width: 168px"
            :value="acc.strategyId || ''"
            :disabled="savingId === acc.id"
            @change="onStrategy(acc, $event)"
          >
            <option value="">暂不绑定</option>
            <option v-for="s in strategies" :key="s.id" :value="s.id">{{ s.name }}</option>
          </select>
        </div>

        <div class="account-row">
          <span class="r-label">自动交易</span>
          <Toggle :checked="acc.autoTrade" @change="(v) => onAuto(acc, v)" />
        </div>

        <div class="account-row">
          <span class="r-label">风险等级</span>
          <Badge tone="warn">{{ acc.risk }}</Badge>
        </div>

        <div class="account-row">
          <span class="r-label">创建时间</span>
          <span style="color: var(--text-3)">{{ acc.created }}</span>
        </div>

        <div v-if="acc.autoTrade && acc.strategyId" style="font-size:11.5px;color:var(--accent-2)">
          自动交易已开启 · 当前策略 {{ strategies.find((s) => s.id === acc.strategyId)?.name }}
        </div>
        <div v-else-if="acc.autoTrade" style="font-size:11.5px;color:var(--warn)">
          提示：开启自动交易需先绑定量化策略
        </div>
      </div>
    </div>

    <!-- 创建账户弹窗 -->
    <Modal :open="showCreate" title="添加交易账户" @close="showCreate = false">
      <Field label="券商 / 账户名称">
        <input v-model="form.broker" class="input" placeholder="如：华泰证券" />
      </Field>
      <div class="grid grid-2" style="gap: 12px">
        <Field label="账户类型">
          <select v-model="form.type" class="select">
            <option>模拟盘</option>
            <option>实盘 · A股</option>
            <option>实盘 · 美股</option>
          </select>
        </Field>
        <Field label="初始资金">
          <input v-model.number="form.capital" type="number" class="input" min="0" />
        </Field>
      </div>
      <Field label="资金账号（可选）">
        <input v-model="form.accountNo" class="input" placeholder="选填，用于展示" />
      </Field>
      <template #footer>
        <Button variant="ghost" @click="showCreate = false">取消</Button>
        <Button :loading="creating" @click="createAccount">确认创建</Button>
      </template>
    </Modal>
  </div>
</template>