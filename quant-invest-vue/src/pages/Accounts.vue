<script setup>
import { ref, computed, onMounted } from 'vue'
import { accountApi } from '../api'
import { fmt } from '../lib/utils'
import { StatCard, Button, Badge, Modal, Field } from '../components/ui'
import Icon from '../components/Icon.vue'
import { useApp } from '../store/app'

const { toast } = useApp()

const CONNECT = {
  untested: { label: '未测试', tone: 'neutral' },
  ok: { label: '连通', tone: 'down' },
  fail: { label: '连接失败', tone: 'up' }
}

const accounts = ref([])
const loading = ref(false)
const testingId = ref(null)

const showCreate = ref(false)
const creating = ref(false)
const form = ref({ name: '', type: '模拟盘', platformUrl: '', loginAccount: '', password: '' })

// 更新登录凭证弹窗（密码留空表示不修改）
const showCred = ref(false)
const credSaving = ref(false)
const credTarget = ref(null)
const credForm = ref({ loginAccount: '', password: '' })

const totalAssets = computed(() => accounts.value.reduce((a, x) => a + x.totalAssets, 0))

async function load() {
  loading.value = true
  accounts.value = await accountApi.list()
  loading.value = false
}

async function testConnection(acc) {
  testingId.value = acc.id
  try {
    const res = await accountApi.testConnection(acc.id)
    acc.connectStatus = res.connectStatus
    acc.lastChecked = res.lastChecked
    if (typeof res.totalAssets === 'number') acc.totalAssets = res.totalAssets
    if (typeof res.cash === 'number') acc.cash = res.cash
    toast(res.message, res.connectStatus === 'ok' ? 'success' : 'error')
  } catch (e) {
    toast(e.message, 'error')
  } finally {
    testingId.value = null
  }
}

function openCred(acc) {
  credTarget.value = acc
  credForm.value = { loginAccount: acc.loginAccount || '', password: '' }
  showCred.value = true
}

async function saveCred() {
  credSaving.value = true
  try {
    const patchBody = { loginAccount: credForm.value.loginAccount }
    if (credForm.value.password) patchBody.password = credForm.value.password
    const updated = await accountApi.update(credTarget.value.id, patchBody)
    const i = accounts.value.findIndex((x) => x.id === credTarget.value.id)
    if (i >= 0) accounts.value[i] = updated
    showCred.value = false
    toast('凭证已更新')
  } catch (e) {
    toast(e.message, 'error')
  } finally {
    credSaving.value = false
  }
}

async function unbind(acc) {
  if (!window.confirm(`确定解绑账户「${acc.name}」吗？解绑后将从账户列表移除，保存的登录凭证一并删除。`)) return
  try {
    await accountApi.remove(acc.id)
    accounts.value = accounts.value.filter((x) => x.id !== acc.id)
    toast('账户已解绑')
  } catch (e) {
    toast(e.message, 'error')
  }
}

async function createAccount() {
  if (!form.value.name.trim()) return toast('请填写账户显示名称', 'error')
  creating.value = true
  try {
    const acc = await accountApi.create({ ...form.value })
    accounts.value.push(acc)
    showCreate.value = false
    form.value = { name: '', type: '模拟盘', platformUrl: '', loginAccount: '', password: '' }
    toast('账户创建成功')
  } finally {
    creating.value = false
  }
}

onMounted(() => {
  load()
})
</script>

<template>
  <div>
    <div class="page-head">
      <div>
        <h1>账户管理</h1>
        <p>连接和管理多个交易账户，连接成功后自动读取账户资金</p>
      </div>
      <div class="page-actions">
        <Button icon="plus" @click="showCreate = true">添加账户</Button>
      </div>
    </div>

    <!-- 概览 -->
    <div class="grid grid-2">
      <StatCard icon="wallet" label="账户总数" :value="accounts.length" sub="实时同步的账户数量" />
      <StatCard icon="account" label="总资产" :value="fmt.money(totalAssets)" sub="全部账户资产合计" />
    </div>

    <!-- 账户卡列表 -->
    <div v-if="loading" style="text-align:center;padding:40px;color:var(--text-3)">账户加载中…</div>
    <div v-else-if="!accounts.length" class="empty-state" style="padding: 48px 20px">
      <Icon name="account" :size="30" />
      <p>暂无账户，点击右上角「添加账户」创建你的第一个交易账户</p>
    </div>
    <div v-else class="grid grid-2 mt-16">
      <div v-for="acc in accounts" :key="acc.id" class="account-card">
        <div class="account-top">
          <div class="account-broker">
            <span class="broker-icon">{{ acc.name.slice(0, 1) }}</span>
            <div>
              <strong>{{ acc.name }}</strong>
              <small>{{ acc.type }}<template v-if="acc.loginAccount"> · {{ acc.loginAccount }}</template></small>
            </div>
          </div>
          <div style="display:flex;align-items:center;gap:8px">
            <Badge :tone="CONNECT[acc.connectStatus]?.tone || 'neutral'" dot>{{ CONNECT[acc.connectStatus]?.label || acc.connectStatus }}</Badge>
            <button type="button" class="icon-btn" title="解绑账户" @click="unbind(acc)">
              <Icon name="close" :size="15" />
            </button>
          </div>
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
          <span class="r-label">账户链接</span>
          <a
            v-if="acc.platformUrl"
            :href="acc.platformUrl"
            target="_blank"
            rel="noopener"
            style="color:var(--accent-2);font-size:12px;max-width:220px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap"
            :title="acc.platformUrl"
          >{{ acc.platformUrl }}</a>
          <span v-else style="color:var(--text-3)">未填写</span>
        </div>

        <div class="account-row">
          <span class="r-label">账户连接</span>
          <div style="display:flex;align-items:center;gap:8px">
            <Button variant="ghost" :loading="testingId === acc.id" @click="testConnection(acc)">测试连接</Button>
            <Button variant="ghost" @click="openCred(acc)">更新凭证</Button>
          </div>
        </div>

        <div class="account-row">
          <span class="r-label">创建时间</span>
          <span style="color: var(--text-3)">{{ acc.created }}<template v-if="acc.lastChecked"> · 上次检测 {{ acc.lastChecked }}</template></span>
        </div>
      </div>
    </div>

    <!-- 创建账户弹窗 -->
    <Modal :open="showCreate" title="添加交易账户" @close="showCreate = false">
      <Field label="账户显示名称">
        <input v-model="form.name" class="input" placeholder="如：我的华泰账户" />
      </Field>
      <Field label="账户类型">
        <select v-model="form.type" class="select">
          <option>模拟盘</option>
          <option>实盘 · A股</option>
          <option>实盘 · 美股</option>
        </select>
      </Field>
      <Field label="账户链接地址">
        <input v-model="form.platformUrl" class="input" placeholder="如：https://trade.example.com" />
      </Field>
      <div class="grid grid-2" style="gap: 12px">
        <Field label="账号">
          <input v-model="form.loginAccount" class="input" placeholder="登录账号 / 资金账号" />
        </Field>
        <Field label="密码">
          <input v-model="form.password" type="password" class="input" placeholder="加密存储，接口不回传" />
        </Field>
      </div>
      <template #footer>
        <Button variant="ghost" @click="showCreate = false">取消</Button>
        <Button :loading="creating" @click="createAccount">确认创建</Button>
      </template>
    </Modal>

    <!-- 更新登录凭证弹窗 -->
    <Modal :open="showCred" :title="`更新登录凭证 · ${credTarget?.name || ''}`" @close="showCred = false">
      <Field label="账号">
        <input v-model="credForm.loginAccount" class="input" placeholder="登录账号 / 资金账号" />
      </Field>
      <Field label="新密码">
        <input v-model="credForm.password" type="password" class="input" placeholder="留空则不修改密码" />
      </Field>
      <template #footer>
        <Button variant="ghost" @click="showCred = false">取消</Button>
        <Button :loading="credSaving" @click="saveCred">保存凭证</Button>
      </template>
    </Modal>
  </div>
</template>
