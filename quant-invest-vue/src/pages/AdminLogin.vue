<script setup>
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { adminApi } from '../api'
import { Button } from '../components/ui'
import Icon from '../components/Icon.vue'

const router = useRouter()
const form = reactive({ username: '', password: '' })
const error = ref('')
const loading = ref(false)

async function submit() {
  error.value = ''
  if (!form.username || !form.password) {
    error.value = '请输入账号和密码'
    return
  }
  loading.value = true
  try {
    const res = await adminApi.login(form)
    localStorage.setItem('admin_token', res.token)
    localStorage.setItem('admin_user', JSON.stringify(res.admin))
    router.push('/admin')
  } catch (err) {
    error.value = err.message
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="admin-login">
    <div class="admin-login-card">
      <div class="admin-brand">
        <span class="logo-mark"><Icon name="shield" :size="22" /></span>
        <div>
          <strong>Iktsuarpok</strong>
          <small>管理后台</small>
        </div>
      </div>

      <h1>管理员登录</h1>
      <p class="sub">使用已授予后台权限的账号登录</p>

      <div v-if="error" class="auth-error">{{ error }}</div>

      <form @submit.prevent="submit">
        <label class="field">
          <span class="field-label">账号</span>
          <input class="input" placeholder="请输入管理员账号" v-model="form.username" autocomplete="username" />
        </label>
        <label class="field">
          <span class="field-label">密码</span>
          <input class="input" type="password" placeholder="请输入管理员密码" v-model="form.password" autocomplete="current-password" />
        </label>
        <Button type="submit" :loading="loading" className="btn-block">登 录</Button>
      </form>

      <p class="admin-hint">
        <Icon name="shield" :size="13" />
        后台账号即平台用户，需具备管理员权限
      </p>
      <p class="auth-foot"><RouterLink to="/login">返回前台登录</RouterLink></p>
    </div>
  </div>
</template>

<style scoped>
.admin-login {
  min-height: 100vh;
  display: grid;
  place-items: center;
  padding: 40px 20px;
  background:
    radial-gradient(800px 460px at 50% 0%, rgba(76, 141, 255, 0.18), transparent 62%),
    radial-gradient(600px 420px at 80% 100%, rgba(166, 107, 255, 0.12), transparent 60%),
    var(--bg);
}
.admin-login-card {
  width: 100%;
  max-width: 380px;
  padding: 30px 28px 24px;
  background: linear-gradient(180deg, var(--panel) 0%, #101728 100%);
  border: 1px solid var(--border);
  border-radius: 16px;
  box-shadow: var(--shadow);
}
.admin-brand { display: flex; align-items: center; gap: 11px; margin-bottom: 26px; }
.admin-brand strong { display: block; font-size: 15px; }
.admin-brand small { display: block; color: var(--text-3); font-size: 11.5px; }
.admin-login-card h1 { font-size: 22px; margin-bottom: 5px; }
.admin-login-card .sub { color: var(--text-2); font-size: 13px; margin-bottom: 22px; }
.admin-hint {
  display: flex; align-items: center; justify-content: center; gap: 6px;
  margin-top: 16px; font-size: 12px; color: var(--text-3);
}
</style>
