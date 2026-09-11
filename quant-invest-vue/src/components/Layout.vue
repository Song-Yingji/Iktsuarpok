<script setup>
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { useApp } from '../store/app'
import { fmt, tone } from '../lib/utils'
import Icon from './Icon.vue'
import { ToastContainer } from './ui'

const NAV = [
  { section: '交易中心' },
  { to: '/market', icon: 'market', label: '行情中心' },
  { to: '/watchlist', icon: 'star', label: '自选股' },
  { to: '/news', icon: 'news', label: '财经新闻' },
  { section: '智能量化' },
  { to: '/agents', icon: 'agent', label: 'AI 智能体' },
  { to: '/strategy', icon: 'strategy', label: '量化策略' },
  { to: '/accounts', icon: 'account', label: '账户管理' },
  { section: '个人' },
  { to: '/preferences', icon: 'prefs', label: '偏好设置' }
]

const { user, toasts, logout, market } = useApp()
const router = useRouter()

const items = computed(() => [...market.value.indices, ...market.value.stocks.slice(0, 8)])
const dupItems = computed(() => [...items.value, ...items.value])

const chgOf = (it) => (it.price - it.prevClose) / it.prevClose

function doLogout() {
  logout()
  router.push('/login')
}
</script>

<template>
  <div class="layout">
    <aside class="sidebar">
      <div class="logo">
        <span class="logo-mark"><Icon name="bolt" :size="18" /></span>
        <div>
          <strong>QuantAI</strong>
          <small>智能量化投资平台</small>
        </div>
      </div>
      <nav class="nav">
        <template v-for="n in NAV" :key="n.to || n.section">
          <div v-if="n.section" class="nav-section">{{ n.section }}</div>
          <RouterLink
            v-else
            :to="n.to"
            class="nav-item"
            active-class="active"
          >
            <Icon :name="n.icon" :size="17" />
            <span>{{ n.label }}</span>
          </RouterLink>
        </template>
      </nav>
      <div class="sidebar-foot">
        <div class="user-box">
          <span class="avatar">{{ user?.avatar || 'U' }}</span>
          <div class="user-meta">
            <strong>{{ user?.username || '投资者' }}</strong>
            <small>专业版 · 已认证</small>
          </div>
          <button class="icon-btn" title="退出登录" @click="doLogout">
            <Icon name="logout" :size="16" />
          </button>
        </div>
      </div>
    </aside>

    <div class="main">
      <header class="topbar">
        <div class="ticker">
          <div class="ticker-track">
            <span v-for="(it, i) in dupItems" :key="it.code + i" class="ticker-item">
              <b>{{ it.name }}</b>
              <span :class="tone(chgOf(it))">{{ fmt.price(it.price) }}</span>
              <span :class="tone(chgOf(it))">{{ fmt.pct(chgOf(it)) }}</span>
            </span>
          </div>
        </div>
        <div class="topbar-right">
          <span class="live-dot"><i />实时行情</span>
          <button class="icon-btn" title="消息通知"><Icon name="bell" :size="17" /></button>
        </div>
      </header>
      <main class="content">
        <router-view />
      </main>
    </div>

    <ToastContainer :toasts="toasts" />
  </div>
</template>