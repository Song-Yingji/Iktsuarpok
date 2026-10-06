<script setup>
import { ref, computed, onMounted } from 'vue'
import { adminApi } from '../../api'
import { Card, Button, Badge, Modal, Field, Toggle } from '../ui'
import Icon from '../Icon.vue'

// 当前登录的后台账号，用于「不能删除自己」的判断
const me = JSON.parse(localStorage.getItem('admin_user') || '{}')

const users = ref([])
const loading = ref(false)
const error = ref('')
const keyword = ref('')

const filtered = computed(() => {
  const kw = keyword.value.trim().toLowerCase()
  if (!kw) return users.value
  return users.value.filter(
    (u) => u.username.toLowerCase().includes(kw) || (u.phone || '').includes(kw)
  )
})

// 权限等级：0 普通用户 / 1 管理员 / 2 超级管理员
const ROLE_USER = 0
const ROLE_ADMIN = 1
const ROLE_SUPER = 2

// 当前账号权限以服务端返回的列表为准，避免本地缓存过期；取不到时按非超级管理员处理
const isSuper = computed(
  () => (users.value.find((u) => u.id === me.id)?.role ?? 0) >= ROLE_SUPER
)

const modalOpen = ref(false)
const saving = ref(false)
const formError = ref('')
const form = ref({ id: null, username: '', password: '', phone: '', role: ROLE_USER })
const isEdit = computed(() => form.value.id != null)

async function load() {
  loading.value = true
  error.value = ''
  try {
    users.value = await adminApi.users()
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

function openCreate() {
  form.value = { id: null, username: '', password: '', phone: '', role: ROLE_USER }
  formError.value = ''
  modalOpen.value = true
}

function openEdit(u) {
  form.value = {
    id: u.id, username: u.username, password: '', phone: u.phone || '', role: u.role
  }
  formError.value = ''
  modalOpen.value = true
}

async function submit() {
  const f = form.value
  formError.value = ''
  if (!f.username.trim()) {
    formError.value = '请填写用户名'
    return
  }
  if (!isEdit.value && !f.password) {
    formError.value = '请填写初始密码'
    return
  }
  if (f.password && f.password.length < 6) {
    formError.value = '密码长度至少 6 位'
    return
  }
  saving.value = true
  try {
    const base = { username: f.username.trim(), phone: f.phone.trim() }
    // 非超级管理员不提交 role，权限变更由后端拒绝
    if (isSuper.value) base.role = f.role
    if (isEdit.value) {
      const payload = { ...base }
      if (f.password) payload.password = f.password
      const updated = await adminApi.updateUser(f.id, payload)
      users.value = users.value.map((u) => (u.id === updated.id ? updated : u))
    } else {
      const created = await adminApi.createUser({ ...base, password: f.password })
      users.value = [...users.value, created]
    }
    modalOpen.value = false
  } catch (e) {
    formError.value = e.message
  } finally {
    saving.value = false
  }
}

async function toggleAdmin(u) {
  if (!isSuper.value || u.role === ROLE_SUPER) return
  error.value = ''
  try {
    const updated = await adminApi.updateUser(u.id, {
      role: u.role >= ROLE_ADMIN ? ROLE_USER : ROLE_ADMIN
    })
    users.value = users.value.map((x) => (x.id === updated.id ? updated : x))
  } catch (e) {
    error.value = e.message
  }
}

async function remove(u) {
  if (!confirm(`确定删除用户「${u.username}」吗？其偏好、策略、账户与自选股将一并删除。`)) return
  error.value = ''
  try {
    await adminApi.removeUser(u.id)
    users.value = users.value.filter((x) => x.id !== u.id)
  } catch (e) {
    error.value = e.message
  }
}

// 普通管理员只能删普通用户；超级管理员、当前登录账号任何情况下都不可删
function canDelete(u) {
  if (u.role === ROLE_SUPER || u.id === me.id) return false
  if (!isSuper.value && u.role >= ROLE_ADMIN) return false
  return true
}

function deleteHint(u) {
  if (u.role === ROLE_SUPER) return '超级管理员不可删除'
  if (u.id === me.id) return '不能删除当前登录账号'
  if (!isSuper.value && u.role >= ROLE_ADMIN) return '仅超级管理员可删除管理员账号'
  return ''
}

function roleTone(u) {
  return u.role === ROLE_SUPER ? 'purple' : u.role === ROLE_ADMIN ? 'info' : 'neutral'
}
function roleText(u) {
  return u.role === ROLE_SUPER ? '超级管理员' : u.role === ROLE_ADMIN ? '管理员' : '普通用户'
}

onMounted(load)
</script>

<template>
  <div>
    <div v-if="error" class="admin-alert">{{ error }}</div>

    <Card title="用户列表" bodyClass="flush">
      <template #extra>
        <div class="users-toolbar">
          <div class="search-box" style="width: 200px">
            <Icon name="search" :size="15" />
            <input class="input" v-model="keyword" placeholder="搜索用户名 / 手机号" />
          </div>
          <Button size="sm" icon="plus" @click="openCreate">新增用户</Button>
        </div>
      </template>

      <div v-if="loading" class="admin-empty">加载中…</div>
      <div v-else-if="!filtered.length" class="empty-state">
        <Icon name="account" :size="28" />
        <p>{{ keyword ? '没有匹配的用户' : '暂无用户' }}</p>
      </div>
      <div v-else style="overflow-x: auto">
        <table class="data-table">
          <thead>
            <tr>
              <th>用户</th>
              <th>手机号</th>
              <th>角色</th>
              <th>后台权限</th>
              <th>创建时间</th>
              <th style="width: 150px"></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="u in filtered" :key="u.id">
              <td>
                <span class="user-cell">
                  <span class="user-avatar">{{ u.avatar || u.username.slice(0, 1).toUpperCase() }}</span>
                  <span class="user-name">{{ u.username }}</span>
                  <Badge v-if="u.id === me.id" tone="neutral">当前账号</Badge>
                </span>
              </td>
              <td>{{ u.phone || '--' }}</td>
              <td><Badge :tone="roleTone(u)">{{ roleText(u) }}</Badge></td>
              <td>
                <span :title="isSuper ? '' : '仅超级管理员可修改权限'">
                  <Toggle
                    :checked="u.role >= ROLE_ADMIN"
                    :disabled="!isSuper || u.role === ROLE_SUPER"
                    @change="toggleAdmin(u)"
                  />
                </span>
              </td>
              <td>{{ u.createdAt }}</td>
              <td>
                <div class="row-actions">
                  <Button size="sm" variant="ghost" icon="prefs" @click="openEdit(u)">编辑</Button>
                  <span :title="deleteHint(u)">
                    <Button
                      size="sm"
                      variant="danger"
                      icon="trash"
                      :disabled="!canDelete(u)"
                      @click="remove(u)"
                    >
                      删除
                    </Button>
                  </span>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </Card>

    <Modal
      :open="modalOpen"
      :title="isEdit ? '编辑用户' : '新增用户'"
      :width="460"
      @close="modalOpen = false"
    >
      <div class="user-form">
        <Field label="用户名">
          <input class="input" v-model="form.username" placeholder="登录用户名" maxlength="50" />
        </Field>
        <Field
          label="密码"
          :hint="isEdit ? '留空表示不修改密码' : '至少 6 位'"
        >
          <input
            class="input"
            type="password"
            v-model="form.password"
            :placeholder="isEdit ? '不修改请留空' : '初始密码'"
          />
        </Field>
        <Field label="手机号（选填）">
          <input class="input" v-model="form.phone" placeholder="1 开头的 11 位手机号" maxlength="11" />
        </Field>
        <div class="form-switch">
          <div>
            <strong>后台管理权限</strong>
            <small>
              {{
                !isSuper
                  ? '仅超级管理员可修改'
                  : form.role === ROLE_SUPER
                    ? '超级管理员权限不可取消'
                    : '开启后可登录后台管理页面'
              }}
            </small>
          </div>
          <Toggle
            :checked="form.role >= ROLE_ADMIN"
            :disabled="!isSuper || form.role === ROLE_SUPER"
            @change="form.role = form.role >= ROLE_ADMIN ? ROLE_USER : ROLE_ADMIN"
          />
        </div>
        <div v-if="formError" class="form-error">{{ formError }}</div>
      </div>

      <template #footer>
        <Button variant="ghost" @click="modalOpen = false">取消</Button>
        <Button :loading="saving" @click="submit">{{ isEdit ? '保存' : '创建' }}</Button>
      </template>
    </Modal>
  </div>
</template>

<style scoped>
.users-toolbar { display: flex; align-items: center; gap: 10px; }
.user-cell { display: inline-flex; align-items: center; gap: 9px; }
.user-avatar {
  width: 28px; height: 28px; border-radius: 50%;
  display: grid; place-items: center; flex: none;
  font-size: 12px; font-weight: 700; color: var(--accent-2);
  background: var(--accent-soft); border: 1px solid var(--border);
}
.user-name { font-weight: 600; }
.row-actions { display: flex; gap: 6px; justify-content: flex-end; }

.user-form { display: flex; flex-direction: column; gap: 14px; }
.form-switch {
  display: flex; align-items: center; justify-content: space-between; gap: 14px;
  padding: 11px 13px; border-radius: 10px;
  background: var(--bg-2); border: 1px solid var(--border);
}
.form-switch strong { display: block; font-size: 13px; }
.form-switch small { display: block; color: var(--text-3); font-size: 11.5px; margin-top: 2px; }
.form-error {
  padding: 9px 12px; border-radius: 8px; font-size: 12.5px;
  background: rgba(246, 70, 93, 0.1); border: 1px solid rgba(246, 70, 93, 0.35);
  color: var(--up);
}
</style>
