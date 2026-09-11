<script setup>
import { ref, onMounted } from 'vue'
import { prefsApi } from '../api'
import { SECTORS, RISK_LEVELS, HORIZONS, BENCHMARKS, DEFAULT_PREFS } from '../lib/constants'
import { Card, Button, Field, Slider, Toggle, Chip } from '../components/ui'
import { useApp } from '../store/app'

const { toast } = useApp()

const RISK_DESC = {
  '保守型': '以保本为主，追求稳健收益',
  '稳健型': '控制回撤，稳健增值',
  '平衡型': '攻守兼备，均衡配置',
  '进取型': '追求较高收益，能承受波动',
  '激进型': '高弹性，高风险高回报'
}

const prefs = ref({ ...DEFAULT_PREFS })
const loading = ref(false)
const saving = ref(false)

async function load() {
  loading.value = true
  prefs.value = { ...DEFAULT_PREFS, ...(await prefsApi.get()) }
  loading.value = false
}

function set(key, val) {
  prefs.value = { ...prefs.value, [key]: val }
}

function toggleSector(sec) {
  const list = [...prefs.value.sectors]
  const i = list.indexOf(sec)
  if (i >= 0) list.splice(i, 1)
  else list.push(sec)
  prefs.value = { ...prefs.value, sectors: list }
}

function reset() {
  prefs.value = { ...DEFAULT_PREFS }
  toast('已恢复默认偏好，点击保存生效')
}

async function save() {
  saving.value = true
  await prefsApi.save(prefs.value)
  saving.value = false
  toast('投资偏好已保存')
}

onMounted(load)
</script>

<template>
  <div>
    <div class="page-head">
      <div>
        <h1>投资偏好设置</h1>
        <p>个性化配置风险偏好、行业偏好与风控参数，智能体将据此为你服务</p>
      </div>
      <div class="page-actions">
        <Button variant="ghost" @click="reset">恢复默认</Button>
        <Button icon="check" :loading="saving" @click="save">保存偏好</Button>
      </div>
    </div>

    <div v-if="loading" style="text-align:center;padding:40px;color:var(--text-3)">偏好加载中…</div>

    <template v-else>
      <!-- 风险等级 -->
      <Card title="风险等级">
        <div class="grid grid-5">
          <div
            v-for="r in RISK_LEVELS"
            :key="r"
            :class="['risk-option', prefs.risk === r && 'selected']"
            @click="set('risk', r)"
          >
            <strong>{{ r }}</strong>
            <small>{{ RISK_DESC[r] }}</small>
          </div>
        </div>
      </Card>

      <div class="grid grid-2 mt-16">
        <!-- 投资期限 -->
        <Card title="投资期限">
          <div class="segmented" style="display:flex">
            <button
              v-for="h in HORIZONS"
              :key="h"
              type="button"
              :class="['seg-item', prefs.horizon === h && 'active']"
              style="flex:1"
              @click="set('horizon', h)"
            >
              {{ h }}
            </button>
          </div>
          <p style="font-size:12px;color:var(--text-3);margin-top:12px">当前：{{ prefs.horizon }}，决定策略的持仓周期与换手频率</p>
        </Card>

        <!-- 业绩基准 -->
        <Card title="业绩比较基准">
          <div class="grid grid-2" style="gap:10px">
            <div
              v-for="b in BENCHMARKS"
              :key="b"
              :class="['risk-option', prefs.benchmark === b && 'selected']"
              @click="set('benchmark', b)"
            >
              <strong>{{ b }}</strong>
            </div>
          </div>
        </Card>
      </div>

      <!-- 行业偏好 -->
      <Card class="mt-16" title="偏好行业（可多选）">
        <div style="display:flex;gap:8px;flex-wrap:wrap">
          <Chip
            v-for="s in SECTORS"
            :key="s"
            :active="prefs.sectors.includes(s)"
            @click="toggleSector(s)"
          >
            {{ s }}
          </Chip>
        </div>
        <p style="font-size:12px;color:var(--text-3);margin-top:12px">
          已选 {{ prefs.sectors.length }} 个行业：{{ prefs.sectors.join('、') || '未选择' }}
        </p>
      </Card>

      <!-- 仓位与风控 -->
      <Card class="mt-16" title="仓位与风控参数">
        <div class="grid grid-2" style="gap:0 32px">
          <Field :label="`单票最大仓位：${prefs.maxPosition}%`" hint="防止单一持仓过度集中">
            <Slider :value="prefs.maxPosition" :min="5" :max="100" :step="5" suffix="%" @change="(v) => set('maxPosition', v)" />
          </Field>
          <Field :label="`止损线：${prefs.stopLoss}%`" hint="亏损达到此比例强制止损">
            <Slider :value="prefs.stopLoss" :min="3" :max="20" :step="1" suffix="%" @change="(v) => set('stopLoss', v)" />
          </Field>
          <Field :label="`止盈线：${prefs.takeProfit}%`" hint="盈利达到此比例分批止盈">
            <Slider :value="prefs.takeProfit" :min="10" :max="100" :step="5" suffix="%" @change="(v) => set('takeProfit', v)" />
          </Field>
        </div>
      </Card>

      <!-- 通知 -->
      <Card class="mt-16" title="自动化与通知">
        <div class="account-row">
          <div style="display:flex;flex-direction:column;gap:3px">
            <span>交易提醒</span>
            <small style="color:var(--text-3);font-size:11.5px">产生交易信号或成交时推送通知</small>
          </div>
          <Toggle :checked="prefs.tradeNotify" @change="(v) => set('tradeNotify', v)" />
        </div>
      </Card>
    </template>
  </div>
</template>