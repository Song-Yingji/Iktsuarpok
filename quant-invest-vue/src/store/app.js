import { reactive, ref } from 'vue'
import { marketApi, strategyApi, newsApi } from '../api'

const user = ref(JSON.parse(localStorage.getItem('quant_user') || 'null'))
const tick = ref(0)
const toasts = reactive([])
const market = ref({ stocks: [], indices: [] })
const marketError = ref('')
const strategies = ref([])
const frameworks = ref([])
const newsCategories = ref(['全部'])

// 静态资源：启动即拉取
strategyApi.list().then((d) => (strategies.value = d)).catch(() => {})
strategyApi.frameworks().then((d) => (frameworks.value = d)).catch(() => {})
newsApi.categories().then((d) => (newsCategories.value = d)).catch(() => {})

// 实时行情：每 2 秒向后端拉取一次快照
async function pollMarket() {
  try {
    const data = await marketApi.getSnapshot()
    market.value = data
    tick.value++
    if (data.realtimeError) marketError.value = '系统繁忙，请稍后重试'
    else if (data.historyError) marketError.value = '服务器开小差了，请稍后重试'
    else marketError.value = ''
  } catch (e) {
    marketError.value = '系统繁忙，请稍后重试'
  }
}
pollMarket()
setInterval(pollMarket, 2000)

function toast(msg, type = 'success') {
  const id = Date.now() + Math.random()
  toasts.push({ id, msg, type })
  setTimeout(() => {
    const i = toasts.findIndex((x) => x.id === id)
    if (i >= 0) toasts.splice(i, 1)
  }, 3200)
}

function login(u, token) {
  localStorage.setItem('quant_user', JSON.stringify(u))
  if (token) localStorage.setItem('quant_token', token)
  user.value = u
}

function logout() {
  localStorage.removeItem('quant_user')
  localStorage.removeItem('quant_token')
  user.value = null
}

export function useApp() {
  return { user, tick, toasts, toast, login, logout, market, marketError, strategies, frameworks, newsCategories }
}