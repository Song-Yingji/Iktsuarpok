import { reactive, ref } from 'vue'
import { marketApi, strategyApi, newsApi } from '../api'

const user = ref(JSON.parse(localStorage.getItem('quant_user') || 'null'))
const tick = ref(0)
const toasts = reactive([])
const market = ref({ stocks: [], indices: [] })
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
    market.value = await marketApi.getSnapshot()
    tick.value++
  } catch (e) {
    /* 网络异常静默处理，等待下次轮询 */
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

function login(u) {
  localStorage.setItem('quant_user', JSON.stringify(u))
  user.value = u
}

function logout() {
  localStorage.removeItem('quant_user')
  user.value = null
}

export function useApp() {
  return { user, tick, toasts, toast, login, logout, market, strategies, frameworks, newsCategories }
}