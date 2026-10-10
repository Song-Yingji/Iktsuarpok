<script setup>
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { Badge, Button, ToastContainer } from '../components/ui'
import Icon from '../components/Icon.vue'
import { useAdminKb } from '../store/admin'
import { useApp } from '../store/app'
import AdminUsers from '../components/admin/AdminUsers.vue'
import AdminDocs from '../components/admin/AdminDocs.vue'
import AdminSearch from '../components/admin/AdminSearch.vue'
import AdminSettings from '../components/admin/AdminSettings.vue'

const router = useRouter()
const admin = JSON.parse(localStorage.getItem('admin_user') || '{}')
const { kbStats } = useAdminKb()
const { toasts } = useApp()

const NAV = [
  { key: 'users', label: '用户管理', icon: 'account', title: '用户管理', desc: '查看全部用户，新增 / 编辑 / 删除账号，设置后台管理权限' },
  { key: 'docs', label: '向量知识库', icon: 'upload', title: '向量知识库', desc: '上传文档 → 递归分块 → 向量化 → 本地持久化' },
  { key: 'search', label: '检索测试', icon: 'search', title: '检索测试', desc: '把问题向量化后在知识库中做相似度比对，预览召回片段' },
  { key: 'settings', label: '模块设置', icon: 'sliders', title: '模块设置', desc: '调整模块化 RAG 检索管线的模块插拔与检索参数' }
]

const active = ref('users')
const current = computed(() => NAV.find((n) => n.key === active.value))

// 上传文档面板：在流程描述末尾补上实际存储位置
const storeDir = computed(() =>
  active.value === 'docs' ? kbStats.value?.storeDir || '' : ''
)

function logout() {
  localStorage.removeItem('admin_token')
  localStorage.removeItem('admin_user')
  router.push('/admin/login')
}
</script>

<template>
  <div class="admin-page">
    <ToastContainer :toasts="toasts" />
    <header class="admin-topbar">
      <div class="admin-topbar-inner">
        <div class="admin-brand">
          <span class="logo-mark"><Icon name="shield" :size="20" /></span>
          <div>
            <strong>Iktsuarpok</strong>
            <small>管理后台</small>
          </div>
        </div>
        <div class="admin-user">
          <span class="admin-name">
            <Icon name="shield" :size="14" />
            {{ admin.username || 'admin' }}
            <Badge :tone="admin.role === 2 ? 'purple' : 'info'">
              {{ admin.role === 2 ? '超级管理员' : '管理员' }}
            </Badge>
          </span>
          <Button size="sm" variant="ghost" icon="logout" @click="logout">退出登录</Button>
        </div>
      </div>
    </header>

    <div class="admin-shell">
      <aside class="admin-side">
        <nav class="admin-nav">
          <button
            v-for="item in NAV"
            :key="item.key"
            :class="['side-link', active === item.key && 'active']"
            @click="active = item.key"
          >
            <Icon :name="item.icon" :size="17" />
            <span>{{ item.label }}</span>
          </button>
        </nav>
      </aside>

      <main class="admin-content">
        <div v-if="active !== 'settings'" class="page-head">
          <div>
            <h1>{{ current.title }}</h1>
            <p>
              {{ current.desc }}<span v-if="storeDir" class="head-path">（{{ storeDir }}）</span>
            </p>
          </div>
        </div>

        <AdminUsers v-if="active === 'users'" />
        <AdminDocs v-else-if="active === 'docs'" />
        <AdminSearch v-else-if="active === 'search'" />
        <AdminSettings v-else />
      </main>
    </div>
  </div>
</template>

<style scoped>
.admin-page { min-height: 100vh; background: var(--bg); }
.admin-topbar {
  position: sticky; top: 0; z-index: 50;
  background: rgba(12, 17, 30, 0.94);
  backdrop-filter: blur(10px);
  border-bottom: 1px solid var(--border);
}
.admin-topbar-inner {
  max-width: 1280px; margin: 0 auto;
  height: 58px; padding: 0 22px;
  display: flex; align-items: center; justify-content: space-between;
}
.admin-brand { display: flex; align-items: center; gap: 11px; }
.admin-brand strong { display: block; font-size: 15px; }
.admin-brand small { display: block; color: var(--text-3); font-size: 11px; }
.admin-user { display: flex; align-items: center; gap: 14px; }
.admin-name {
  display: flex; align-items: center; gap: 7px;
  font-size: 13px; color: var(--text-2);
}

.admin-shell {
  max-width: 1280px; margin: 0 auto; padding: 22px;
  display: flex; align-items: flex-start; gap: 20px;
}
.admin-side {
  flex: none; width: 208px;
  position: sticky; top: 80px;
}
.admin-nav { display: flex; flex-direction: column; gap: 6px; }
.side-link {
  display: flex; align-items: center; gap: 10px;
  width: 100%; padding: 11px 13px;
  border: 1px solid transparent; border-radius: 10px;
  background: var(--panel); color: var(--text-2);
  font-size: 13.5px; font-family: inherit; text-align: left;
  cursor: pointer; transition: all 0.16s;
}
.side-link:hover { color: var(--text); border-color: var(--border); }
.side-link.active {
  color: var(--accent-2);
  background: var(--accent-soft);
  border-color: rgba(76, 141, 255, 0.4);
  font-weight: 600;
}
.admin-content { flex: 1 1 auto; min-width: 0; }
.admin-content .page-head { margin-bottom: 16px; }
.head-path {
  font-family: 'JetBrains Mono', Consolas, monospace;
  font-size: 11.5px; color: var(--text-3); word-break: break-all;
}

@media (max-width: 900px) {
  .admin-shell { flex-direction: column; padding: 16px; }
  .admin-side { width: 100%; position: static; }
  .admin-nav { flex-direction: row; overflow-x: auto; }
  .side-link { width: auto; white-space: nowrap; }
}
</style>
