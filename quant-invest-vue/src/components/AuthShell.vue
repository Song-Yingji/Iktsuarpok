<script setup>
import { reactive, ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useApp } from '../store/app'
import { authApi } from '../api'
import { Button } from './ui'
import Icon from './Icon.vue'

const props = defineProps({ mode: { type: String, default: 'login' } })
const isLogin = computed(() => props.mode === 'login')

const FEATURES = [
  { icon: 'market', text: '实时行情与 Level-1 数据推送，秒级刷新大盘与个股动态' },
  { icon: 'agent', text: 'AI 智能体自动荐股，自然语言一键生成量化策略' },
  { icon: 'strategy', text: '内置回测引擎：买卖点标记、夏普比率、CVaR、最大回撤' },
  { icon: 'bolt', text: '策略绑定证券账户，开启自动交易，7×24 无人值守' }
]

const { login } = useApp()
const router = useRouter()
const form = reactive({ username: '', password: '', phone: '', confirm: '' })
const error = ref('')
const loading = ref(false)

async function submit() {
  error.value = ''
  if (!isLogin.value && form.password !== form.confirm) {
    error.value = '两次输入的密码不一致'
    return
  }
  loading.value = true
  try {
    const res = isLogin.value ? await authApi.login(form) : await authApi.register(form)
    login(res.user, res.token)
    router.push('/market')
  } catch (err) {
    error.value = err.message
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="auth-page">
    <div class="auth-hero">
      <div class="auth-brand">
        <span class="logo-mark"><Icon name="bolt" :size="22" /></span>
        <strong>Iktsuarpok 智能量化投资平台</strong>
      </div>
      <h2>让 AI 为你<br /><span>量化每一次投资决策</span></h2>
      <p>融合实时行情、财经资讯、智能荐股与策略回测的一站式量化交易平台，从信号发现到自动下单全链路覆盖。</p>
      <div class="auth-features">
        <div v-for="f in FEATURES" :key="f.icon" class="auth-feature">
          <Icon :name="f.icon" :size="17" />
          <span>{{ f.text }}</span>
        </div>
      </div>
    </div>

    <div class="auth-side">
      <div class="auth-card">
        <h1>{{ isLogin ? '欢迎回来' : '创建账户' }}</h1>
        <p class="sub">{{ isLogin ? '登录后进入你的量化交易工作台' : '注册即可体验 AI 智能量化投研' }}</p>

        <div class="auth-tabs">
          <RouterLink to="/login" :class="['auth-tab', isLogin && 'active']">登录</RouterLink>
          <RouterLink to="/register" :class="['auth-tab', !isLogin && 'active']">注册</RouterLink>
        </div>

        <div v-if="error" class="auth-error">{{ error }}</div>

        <form @submit.prevent="submit">
          <label class="field">
            <span class="field-label">用户名</span>
            <input class="input" placeholder="请输入用户名" v-model="form.username" />
          </label>
          <label v-if="!isLogin" class="field">
            <span class="field-label">手机号</span>
            <input class="input" placeholder="用于接收交易提醒（选填）" v-model="form.phone" />
          </label>
          <label class="field">
            <span class="field-label">密码</span>
            <input class="input" type="password" placeholder="至少 6 位密码" v-model="form.password" />
          </label>
          <label v-if="!isLogin" class="field">
            <span class="field-label">确认密码</span>
            <input class="input" type="password" placeholder="再次输入密码" v-model="form.confirm" />
          </label>
          <Button type="submit" :loading="loading" className="btn-block">
            {{ isLogin ? '登 录' : '注 册' }}
          </Button>
        </form>

        <p class="auth-foot">
          <template v-if="isLogin">
            还没有账户？<RouterLink to="/register">立即注册</RouterLink>
          </template>
          <template v-else>
            已有账户？<RouterLink to="/login">返回登录</RouterLink>
          </template>
        </p>
        <p class="auth-foot" style="margin-top: 8px; font-size: 12px">
          登录需已注册账户，注册后数据将安全保存到你的账户
        </p>
      </div>
    </div>
  </div>
</template>