<script setup>
import { ref, onMounted } from 'vue'
import { prefsApi } from '../api'
import { SECTORS, RISK_LEVELS, HORIZONS, BENCHMARKS, DEFAULT_PREFS } from '../lib/constants'
import { Card, Button, Badge, Field, Slider, Chip, Modal } from '../components/ui'
import Icon from '../components/Icon.vue'
import { useApp } from '../store/app'

const { toast } = useApp()

const RISK_DESC = {
  '保守型': '以保本为主，追求稳健收益',
  '稳健型': '控制回撤，稳健增值',
  '平衡型': '攻守兼备，均衡配置',
  '进取型': '追求较高收益，能承受波动',
  '激进型': '高弹性，高风险高回报'
}

const sets = ref([])
const loading = ref(false)
const saving = ref(false)
const showForm = ref(false)
const editingId = ref(null)   // null 表示新增
const form = ref({ ...DEFAULT_PREFS, name: '' })
const sectorView = ref(null)  // 查看完整关注行业的偏好，null 表示未打开
const SECTOR_PREVIEW = 3      // 卡片上最多展示的关注行业数量

async function load() {
  loading.value = true
  try {
    sets.value = await prefsApi.list()
  } catch (e) {
    toast(e.message, 'error')
  } finally {
    loading.value = false
  }
}

function openCreate() {
  editingId.value = null
  form.value = { ...DEFAULT_PREFS, sectors: [...DEFAULT_PREFS.sectors], name: '' }
  showForm.value = true
}

function openEdit(item) {
  editingId.value = item.id
  form.value = {
    name: item.name,
    risk: item.risk,
    horizon: item.horizon,
    benchmark: item.benchmark,
    sectors: [...item.sectors],
    maxPosition: item.maxPosition,
    stopLoss: item.stopLoss,
    takeProfit: item.takeProfit
  }
  showForm.value = true
}

// 关闭即放弃编辑：未点保存不落库
function closeForm() {
  showForm.value = false
}

function set(key, val) {
  form.value = { ...form.value, [key]: val }
}

function toggleSector(sec) {
  const list = [...form.value.sectors]
  const i = list.indexOf(sec)
  if (i >= 0) list.splice(i, 1)
  else list.push(sec)
  form.value = { ...form.value, sectors: list }
}

function openSectors(p) {
  if (p.sectors.length <= SECTOR_PREVIEW) return
  sectorView.value = p
}

async function saveForm() {
  if (!(form.value.name || '').trim()) return toast('请填写偏好名称', 'error')
  saving.value = true
  try {
    if (editingId.value) {
      await prefsApi.update(editingId.value, form.value)
      toast('偏好已更新')
    } else {
      await prefsApi.create(form.value)
      toast('偏好已保存')
    }
    showForm.value = false
    await load()
  } catch (e) {
    toast(e.message, 'error')
  } finally {
    saving.value = false
  }
}

async function setDefault(item) {
  if (item.isDefault) return
  try {
    await prefsApi.setDefault(item.id)
    // 就地更新默认标记，避免重新拉取列表导致卡片位置跳动
    sets.value = sets.value.map((p) => ({ ...p, isDefault: p.id === item.id }))
    toast(`已将「${item.name}」设为默认偏好`)
  } catch (e) {
    toast(e.message, 'error')
  }
}

async function remove(item) {
  if (!window.confirm(`确定删除偏好「${item.name}」吗？`)) return
  try {
    await prefsApi.remove(item.id)
    await load()
    toast('偏好已删除')
  } catch (e) {
    toast(e.message, 'error')
  }
}

onMounted(load)
</script>

<template>
  <div>
    <div class="page-head">
      <div>
        <h1>投资偏好设置</h1>
        <p>可保存多套偏好用于不同场景，自动荐股时选择其中一套使用</p>
      </div>
      <div class="page-actions">
        <Button icon="plus" @click="openCreate">添加偏好</Button>
      </div>
    </div>

    <div v-if="loading" style="text-align:center;padding:40px;color:var(--text-3)">偏好加载中…</div>

    <div v-else-if="!sets.length" class="empty-state" style="padding:48px 20px">
      <Icon name="prefs" :size="30" />
      <p>还没有保存任何偏好，点击右上角「添加偏好」创建第一套</p>
    </div>

    <div v-else class="grid grid-2">
      <Card v-for="p in sets" :key="p.id">
        <template #title>
          <span style="display:flex;align-items:center;gap:8px">
            {{ p.name }}
            <Badge v-if="p.isDefault" tone="up">默认</Badge>
          </span>
        </template>
        <template #extra>
          <span style="font-size:11.5px;color:var(--text-3)">更新于 {{ p.updatedAt }}</span>
        </template>

        <div class="pref-tags">
          <Badge tone="info">{{ p.risk }}</Badge>
          <Badge tone="neutral">{{ p.horizon }}</Badge>
          <Badge tone="neutral">基准 {{ p.benchmark }}</Badge>
        </div>

        <div class="pref-label">关注行业</div>
        <div style="display:flex;gap:6px;flex-wrap:wrap;align-items:center">
          <template v-if="p.sectors.length">
            <Chip v-for="s in p.sectors.slice(0, SECTOR_PREVIEW)" :key="s" :active="true">{{ s }}</Chip>
            <button
              v-if="p.sectors.length > SECTOR_PREVIEW"
              class="more-chip"
              :title="`查看全部 ${p.sectors.length} 个关注行业`"
              @click="openSectors(p)"
            >
              +{{ p.sectors.length - SECTOR_PREVIEW }}
            </button>
          </template>
          <span v-else style="font-size:12px;color:var(--text-3)">不限</span>
        </div>

        <div class="pref-nums">
          <div><span>单票最大仓位</span><b>{{ p.maxPosition }}%</b></div>
          <div><span>止损线</span><b>{{ p.stopLoss }}%</b></div>
          <div><span>止盈线</span><b>{{ p.takeProfit }}%</b></div>
        </div>

        <div class="pref-actions">
          <Button size="sm" variant="ghost" @click="openEdit(p)">编辑</Button>
          <Button size="sm" variant="ghost" icon="star" :disabled="p.isDefault" @click="setDefault(p)">
            {{ p.isDefault ? '已是默认' : '设为默认' }}
          </Button>
          <Button size="sm" variant="ghost" @click="remove(p)">删除</Button>
        </div>
      </Card>
    </div>

    <!-- 添加 / 编辑偏好：点保存才落库，关闭即放弃 -->
    <Modal :open="showForm" :title="editingId ? '编辑偏好' : '添加偏好'" :width="640" @close="closeForm">
      <Field label="偏好名称">
        <input v-model="form.name" class="input" placeholder="如：稳健长线、激进短线" maxlength="20" />
      </Field>

      <div class="pref-label mt-16">风险等级</div>
      <div class="grid grid-5">
        <div
          v-for="r in RISK_LEVELS"
          :key="r"
          :class="['risk-option', form.risk === r && 'selected']"
          @click="set('risk', r)"
        >
          <strong>{{ r }}</strong>
          <small>{{ RISK_DESC[r] }}</small>
        </div>
      </div>

      <div class="pref-label mt-16">投资期限</div>
      <div class="segmented" style="display:flex">
        <button
          v-for="h in HORIZONS"
          :key="h"
          type="button"
          :class="['seg-item', form.horizon === h && 'active']"
          style="flex:1"
          @click="set('horizon', h)"
        >
          {{ h }}
        </button>
      </div>

      <div class="pref-label mt-16">业绩比较基准</div>
      <div class="grid grid-4" style="gap:10px">
        <div
          v-for="b in BENCHMARKS"
          :key="b"
          :class="['risk-option', form.benchmark === b && 'selected']"
          @click="set('benchmark', b)"
        >
          <strong>{{ b }}</strong>
        </div>
      </div>

      <div class="pref-label mt-16">偏好行业（可多选）</div>
      <div style="display:flex;gap:8px;flex-wrap:wrap">
        <Chip
          v-for="s in SECTORS"
          :key="s"
          :active="form.sectors.includes(s)"
          @click="toggleSector(s)"
        >
          {{ s }}
        </Chip>
      </div>

      <div class="grid grid-2" style="gap:0 32px;margin-top:16px">
        <Field :label="`单票最大仓位：${form.maxPosition}%`" hint="防止单一持仓过度集中">
          <Slider :value="form.maxPosition" :min="5" :max="100" :step="5" suffix="%" @change="(v) => set('maxPosition', v)" />
        </Field>
        <Field :label="`止损线：${form.stopLoss}%`" hint="亏损达到此比例强制止损">
          <Slider :value="form.stopLoss" :min="3" :max="20" :step="1" suffix="%" @change="(v) => set('stopLoss', v)" />
        </Field>
        <Field :label="`止盈线：${form.takeProfit}%`" hint="盈利达到此比例分批止盈">
          <Slider :value="form.takeProfit" :min="10" :max="100" :step="5" suffix="%" @change="(v) => set('takeProfit', v)" />
        </Field>
      </div>

      <template #footer>
        <Button variant="ghost" @click="closeForm">取消</Button>
        <Button icon="check" :loading="saving" @click="saveForm">保存</Button>
      </template>
    </Modal>

    <!-- 查看某套偏好的完整关注行业 -->
    <Modal
      :open="!!sectorView"
      :title="sectorView ? `关注行业 · ${sectorView.name}` : ''"
      :width="480"
      @close="sectorView = null"
    >
      <div style="display:flex;gap:8px;flex-wrap:wrap">
        <Chip v-for="s in sectorView?.sectors || []" :key="s" :active="true">{{ s }}</Chip>
      </div>
      <template #footer>
        <Button variant="ghost" @click="sectorView = null">关闭</Button>
      </template>
    </Modal>
  </div>
</template>

<style scoped>
.pref-tags { display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 12px; }
.pref-label { font-size: 12.5px; color: var(--text-2); margin-bottom: 8px; }
.more-chip {
  padding: 6px 12px;
  border-radius: 20px;
  background: transparent;
  border: 1px dashed var(--border-light);
  color: var(--text-3);
  font-size: 12.5px;
  transition: all 0.15s;
}
.more-chip:hover { border-color: var(--accent); color: var(--accent-2); }
.pref-nums {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 10px;
  margin: 14px 0;
  padding: 10px 12px;
  background: var(--panel-2);
  border-radius: 8px;
}
.pref-nums div { display: flex; flex-direction: column; gap: 3px; }
.pref-nums span { font-size: 11.5px; color: var(--text-3); }
.pref-nums b { font-size: 14px; }
.pref-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding-top: 12px;
  border-top: 1px solid var(--border);
}
</style>
