// ============================================================
// 前端 API 层：通过 HTTP 对接 Node/Express 后端
// 后端地址可通过环境变量 VITE_API_BASE 覆盖，默认本地 3000 端口
// ============================================================
const BASE_URL = import.meta.env.VITE_API_BASE || 'http://localhost:3000/api'

async function request(path, options = {}) {
  const method = options.method || 'GET'
  let res
  try {
    res = await fetch(BASE_URL + path, {
      method,
      headers: { 'Content-Type': 'application/json' },
      body: options.body ? JSON.stringify(options.body) : undefined
    })
  } catch (e) {
    throw new Error('无法连接后端服务，请确认服务已启动')
  }
  const data = await res.json().catch(() => ({}))
  if (!res.ok) throw new Error(data.message || `请求失败 (${res.status})`)
  return data
}

// ---------------- 鉴权 ----------------
export const authApi = {
  login: (payload) => request('/auth/login', { method: 'POST', body: payload }),
  register: (payload) => request('/auth/register', { method: 'POST', body: payload })
}

// ---------------- 行情 ----------------
export const marketApi = {
  getSnapshot: () => request('/market/snapshot'),
  getKline: (code) => request('/market/kline/' + encodeURIComponent(code))
}

// ---------------- 新闻 ----------------
export const newsApi = {
  async list({ category, keyword } = {}) {
    const qs = new URLSearchParams()
    if (category) qs.set('category', category)
    if (keyword) qs.set('keyword', keyword)
    const q = qs.toString()
    return request('/news' + (q ? '?' + q : ''))
  },
  categories: () => request('/news/categories')
}

// ---------------- 投资偏好 ----------------
export const prefsApi = {
  get: () => request('/prefs'),
  save: (prefs) => request('/prefs', { method: 'POST', body: prefs })
}

// ---------------- 智能体 ----------------
export const agentApi = {
  recommend: (prefs) => request('/agent/recommend', { method: 'POST', body: prefs }),
  generateStrategy: (prompt) => request('/agent/generate-strategy', { method: 'POST', body: { prompt } })
}

// ---------------- 策略 / 回测 ----------------
export const strategyApi = {
  list: () => request('/strategy'),
  frameworks: () => request('/strategy/frameworks')
}

export const runBacktest = (payload) => request('/strategy/backtest', { method: 'POST', body: payload })

// ---------------- 账户 ----------------
export const accountApi = {
  list: () => request('/accounts'),
  update: (id, patch) => request('/accounts/' + id, { method: 'PUT', body: patch }),
  create: (payload) => request('/accounts', { method: 'POST', body: payload })
}

// ---------------- 持仓 / 资产 ----------------
export const positionApi = {
  get: () => request('/positions')
}