<script setup>
import { ref, onMounted } from 'vue'
import { quantTaskApi, watchlistApi, strategyApi, accountApi, settingsApi } from '../api'
import { useApp } from '../store/app'
import { Card, Button, Badge, Toggle, Modal, Chip } from '../components/ui'
import Icon from '../components/Icon.vue'

const { toast } = useApp()

const tasks = ref([])
const stocks = ref([]) // 自选股 {code, name}
const strategies = ref([]) // 已保存的量化策略 {id, name}
const accounts = ref([]) // 交易账户 {id, name}
const settings = ref({ tradeNotify: true })
const loading = ref(false)
const adding = ref(false)
const savingId = ref(null)

const STOCK_PREVIEW = 3 // 任务卡片上最多展示的投资标的数量
const stockView = ref(null) // 查看完整标的列表的任务，null 表示未打开

// 编辑弹窗
const editOpen = ref(false)
const editTaskId = ref(null)
const draft = ref({ stockCodes: [], strategyId: null, accountId: null })

async function load() {
  loading.value = true
  const [ts, wl, saved, accs, st] = await Promise.all([
    quantTaskApi.list(),
    watchlistApi.list(),
    strategyApi.saved(),
    accountApi.list(),
    settingsApi.get()
  ])
  tasks.value = ts
  stocks.value = wl
  strategies.value = saved
  accounts.value = accs
  settings.value = st
  loading.value = false
}

async function addTask() {
  adding.value = true
  try {
    const t = await quantTaskApi.create()
    tasks.value.push(t)
  } catch (e) {
    toast(e.message, 'error')
  } finally {
    adding.value = false
  }
}

async function saveTask(task, patch, silent = false) {
  if (!silent) savingId.value = task.id
  try {
    const updated = await quantTaskApi.update(task.id, patch)
    const i = tasks.value.findIndex((x) => x.id === task.id)
    if (i >= 0) tasks.value[i] = updated
    return updated
  } catch (e) {
    toast(e.message, 'error')
  } finally {
    if (!silent) savingId.value = null
  }
}

async function removeTask(idx) {
  const task = tasks.value[idx]
  if (!confirm(`确定删除交易任务 ${idx + 1} 吗？`)) return
  try {
    await quantTaskApi.remove(task.id)
    tasks.value = tasks.value.filter((x) => x.id !== task.id)
    toast('交易任务已删除')
  } catch (e) {
    toast(e.message, 'error')
  }
}

async function onTradeNotify(checked) {
  try {
    await settingsApi.save({ tradeNotify: checked })
    settings.value = { ...settings.value, tradeNotify: checked }
    toast(checked ? '已开启交易提醒' : '已关闭交易提醒')
  } catch (e) {
    toast(e.message, 'error')
  }
}

// ===== 自动交易：有标的 + 有策略 + 有账户才可开启 =====
function canAuto(t) {
  return !!(t.stockCodes && t.stockCodes.length && t.strategyId && t.accountId)
}

async function onAutoTrade(idx, checked) {
  const task = tasks.value[idx]
  if (checked && !canAuto(task)) {
    toast('需同时选择投资标的、量化策略和交易账户后才能开启自动交易', 'error')
    return
  }
  await saveTask(task, { autoTrade: checked }, true)
}

// ===== 编辑弹窗 =====
async function openEdit(idx) {
  const task = tasks.value[idx]
  if (task.autoTrade) {
    await saveTask(task, { autoTrade: false }, true)
    toast('进入编辑前已自动关闭自动交易')
  }
  editTaskId.value = task.id
  draft.value = {
    stockCodes: [...task.stockCodes],
    strategyId: task.strategyId,
    accountId: task.accountId
  }
  editOpen.value = true
}

function closeEdit() {
  editOpen.value = false
  editTaskId.value = null
}

function toggleDraftCode(code) {
  const codes = new Set(draft.value.stockCodes)
  if (codes.has(code)) codes.delete(code)
  else codes.add(code)
  draft.value = { ...draft.value, stockCodes: [...codes] }
}

function onDraftStrategy(e) {
  const v = e.target.value
  draft.value = { ...draft.value, strategyId: v ? Number(v) : null }
}

function onDraftAccount(e) {
  const v = e.target.value
  draft.value = { ...draft.value, accountId: v ? Number(v) : null }
}

async function saveEdit() {
  const task = tasks.value.find((x) => x.id === editTaskId.value)
  if (!task) return closeEdit()
  const patch = {
    stockCodes: draft.value.stockCodes,
    strategyId: draft.value.strategyId,
    accountId: draft.value.accountId
  }
  if (!canAuto(patch)) patch.autoTrade = false // 配置不全时保持自动交易关闭
  const updated = await saveTask(task, patch)
  if (updated) toast('交易任务已保存')
  closeEdit()
}

// ===== 展示辅助 =====
const codeName = (c) => {
  const s = stocks.value.find((x) => x.code === c)
  return s ? s.name : c + '(已移出)'
}
const strategyName = (t) => {
  const s = strategies.value.find((x) => x.id === t.strategyId)
  return s ? s.name : '策略已删除'
}
const accountName = (t) => {
  const a = accounts.value.find((x) => x.id === t.accountId)
  return a ? a.name : '账户已删除'
}

// 查看完整投资标的列表（超过预览数量才可点开）
function openStocks(idx) {
  const task = tasks.value[idx]
  if (task.stockCodes.length <= STOCK_PREVIEW) return
  stockView.value = { idx, codes: task.stockCodes }
}

onMounted(load)
</script>

<template>
  <div>
    <div class="page-head">
      <div>
        <h1>量化交易</h1>
        <p>创建量化交易任务：为自选股绑定量化策略与交易账户，开启自动交易</p>
      </div>
      <div class="page-actions">
        <Button icon="plus" :loading="adding" @click="addTask">新增交易任务</Button>
      </div>
    </div>

    <!-- 交易提醒 -->
    <Card>
      <div class="account-row">
        <div style="display:flex;flex-direction:column;gap:3px">
          <span>交易提醒</span>
          <small style="color:var(--text-3);font-size:11.5px">产生交易信号或成交时推送通知</small>
        </div>
        <Toggle :checked="settings.tradeNotify" @change="onTradeNotify" />
      </div>
    </Card>

    <!-- 任务列表 -->
    <div v-if="loading" class="empty-state" style="padding: 40px">加载中…</div>
    <div v-else-if="!tasks.length" class="empty-state" style="padding: 48px 20px">
      <Icon name="chart" :size="30" />
      <p>暂无量化交易任务，点击右上角「新增交易任务」创建</p>
    </div>
    <div v-else class="task-list">
      <Card v-for="(task, idx) in tasks" :key="task.id">
        <!-- 第一行：任务编号 + 时间 -->
        <div class="t-head">
          <strong>交易任务 {{ idx + 1 }}</strong>
          <Badge v-if="savingId === task.id" tone="info" dot>保存中</Badge>
          <span class="t-date">{{ task.created }}</span>
        </div>

        <!-- 第二行：配置摘要 + 操作 -->
        <div class="t-body">
          <div class="seg">
            <span class="seg-label">投资标的</span>
            <div class="tag-row">
              <template v-if="task.stockCodes.length">
                <Chip
                  v-for="c in task.stockCodes.slice(0, STOCK_PREVIEW)"
                  :key="c"
                  :active="true"
                >{{ codeName(c) }}</Chip>
                <button
                  v-if="task.stockCodes.length > STOCK_PREVIEW"
                  class="more-chip"
                  :title="`查看全部 ${task.stockCodes.length} 个投资标的`"
                  @click="openStocks(idx)"
                >
                  +{{ task.stockCodes.length - STOCK_PREVIEW }}
                </button>
              </template>
              <span v-else class="seg-empty">未选择</span>
            </div>
          </div>
          <div class="seg">
            <span class="seg-label">量化策略</span>
            <div class="tag-row">
              <Chip
                v-if="task.strategyId"
                :active="true"
                :class="{ 'tag-lost': !strategies.some((s) => s.id === task.strategyId) }"
              >{{ strategyName(task) }}</Chip>
              <span v-else class="seg-empty">未绑定</span>
            </div>
          </div>
          <div class="seg">
            <span class="seg-label">交易账户</span>
            <div class="tag-row">
              <Chip
                v-if="task.accountId"
                :active="true"
                :class="{ 'tag-lost': !accounts.some((a) => a.id === task.accountId) }"
              >{{ accountName(task) }}</Chip>
              <span v-else class="seg-empty">未选择</span>
            </div>
          </div>

          <div class="seg t-auto">
            <span class="seg-label">自动交易</span>
            <Toggle :checked="task.autoTrade" :disabled="!canAuto(task) && !task.autoTrade" @change="onAutoTrade(idx, $event)" />
          </div>

          <div class="t-ops">
            <button class="icon-btn" title="修改任务" @click="openEdit(idx)">
              <Icon name="sliders" :size="15" />
            </button>
            <button class="icon-btn" title="删除任务" @click="removeTask(idx)">
              <Icon name="trash" :size="15" />
            </button>
          </div>
        </div>
      </Card>
    </div>

    <!-- 编辑弹窗 -->
    <Modal :open="editOpen" title="编辑交易任务" @close="closeEdit">
      <div class="edit-sec">
        <div class="field-label">投资标的（可多选）</div>
        <div class="pick-wrap">
          <button
            v-for="s in stocks"
            :key="s.code"
            class="pick-chip"
            :class="{ on: draft.stockCodes.includes(s.code) }"
            @click="toggleDraftCode(s.code)"
          >{{ s.name }}（{{ s.code }}）</button>
          <span v-if="!stocks.length" class="pick-hint">暂无自选股，可先到「自选股」页添加</span>
        </div>
      </div>

      <div class="edit-sec">
        <div class="field-label">量化策略</div>
        <select class="select" :value="draft.strategyId || ''" @change="onDraftStrategy">
          <option value="">暂不绑定</option>
          <option v-for="s in strategies" :key="s.id" :value="s.id">{{ s.name }}</option>
        </select>
      </div>

      <div class="edit-sec">
        <div class="field-label">交易账户</div>
        <select class="select" :value="draft.accountId || ''" @change="onDraftAccount">
          <option value="">暂不选择</option>
          <option v-for="a in accounts" :key="a.id" :value="a.id">{{ a.name }}</option>
        </select>
      </div>

      <p class="edit-hint">需同时选择投资标的、量化策略和交易账户，才可开启自动交易</p>

      <template #footer>
        <Button variant="ghost" @click="closeEdit">取消</Button>
        <Button icon="check" @click="saveEdit">保存</Button>
      </template>
    </Modal>

    <!-- 查看全部投资标的 -->
    <Modal
      :open="!!stockView"
      :title="stockView ? `投资标的 · 交易任务 ${stockView.idx + 1}` : ''"
      :width="480"
      @close="stockView = null"
    >
      <div class="stock-all">
        <Chip v-for="c in stockView?.codes || []" :key="c" :active="true">{{ codeName(c) }}</Chip>
      </div>
      <template #footer>
        <Button variant="ghost" @click="stockView = null">关闭</Button>
      </template>
    </Modal>
  </div>
</template>

<style scoped>
.task-list { display: flex; flex-direction: column; gap: 12px; margin-top: 16px; }

/* 第一行：任务编号 + 时间 */
.t-head { display: flex; align-items: center; gap: 10px; }
.t-head strong { font-size: 14px; letter-spacing: 0.2px; }
.t-date { font-size: 11px; color: var(--text-3); }

/* 第二行：配置摘要 + 操作（三栏固定列宽，跨任务对齐） */
.t-body {
  display: grid;
  grid-template-columns: 330px 190px 190px 1fr auto;
  align-items: end; gap: 14px 24px;
  margin-top: 12px; padding-top: 14px;
  border-top: 1px solid rgba(32, 44, 71, 0.6);
}

.seg { display: flex; flex-direction: column; gap: 7px; min-width: 0; }
.seg-label {
  font-size: 13px; font-weight: 500; color: var(--text-2);
  letter-spacing: 0.3px; white-space: nowrap;
}
.seg-empty { font-size: 13px; color: var(--text-3); line-height: 1.5; }

/* 标签框：标的 / 策略 / 账户统一用 chip 展示 */
.tag-row {
  display: flex; flex-wrap: wrap; gap: 6px; align-items: center;
  min-height: 28px;
}
.tag-row .chip {
  max-width: 100%; overflow: hidden;
  text-overflow: ellipsis; white-space: nowrap;
}
.tag-lost {
  border-color: var(--warn) !important;
  color: var(--warn) !important;
  background: transparent !important;
}
/* 投资标的：预览 3 个，多余折叠为 +N */
.more-chip {
  padding: 4px 11px; border-radius: 20px; cursor: pointer;
  background: transparent; border: 1px dashed var(--border-light);
  color: var(--text-3); font-size: 12px;
  transition: all 0.15s;
}
.more-chip:hover { border-color: var(--accent); color: var(--accent-2); }
.stock-all { display: flex; gap: 8px; flex-wrap: wrap; }

.t-auto { justify-self: end; padding-bottom: 2px; }

.t-ops { display: flex; align-items: center; gap: 6px; padding-bottom: 2px; }

/* 编辑弹窗 */
.edit-sec { margin-bottom: 16px; }
.edit-sec .field-label { margin-bottom: 8px; }

.pick-wrap { display: flex; flex-wrap: wrap; gap: 8px; }
.pick-chip {
  padding: 5px 12px; border-radius: 999px; cursor: pointer;
  font-size: 12px; line-height: 1.4;
  color: var(--text-2); background: transparent;
  border: 1px solid var(--border-light);
  transition: all 0.15s;
}
.pick-chip:hover { border-color: var(--accent); color: var(--accent-2); }
.pick-chip.on {
  color: var(--accent-2); border-color: var(--accent);
  background: rgba(56, 225, 255, 0.1);
}
.pick-hint { font-size: 11.5px; color: var(--text-3); }

.edit-hint { font-size: 11.5px; color: var(--text-3); margin: 4px 0 0; }
</style>
