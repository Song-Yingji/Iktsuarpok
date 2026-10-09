// ============================================================
// 前端 API 层：通过 HTTP 对接 Python/FastAPI 后端
// 后端地址可通过环境变量 VITE_API_BASE 覆盖，默认本地 3000 端口
// ============================================================
const BASE_URL = import.meta.env.VITE_API_BASE || 'http://localhost:3000/api'

// 普通用户与后台管理员各自独立保存 token，互不影响
const SCOPES = {
  user: { token: 'quant_token', user: 'quant_user', login: '/login', public: ['/login', '/register'] },
  admin: { token: 'admin_token', user: 'admin_user', login: '/admin/login', public: ['/admin/login'] }
}

function onUnauthorized(scope) {
  localStorage.removeItem(scope.token)
  localStorage.removeItem(scope.user)
  if (!scope.public.includes(location.pathname)) location.href = scope.login
}

async function request(path, options = {}) {
  const method = options.method || 'GET'
  const scope = SCOPES[options.scope] || SCOPES.user
  const token = localStorage.getItem(scope.token)
  let res
  try {
    res = await fetch(BASE_URL + path, {
      method,
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: 'Bearer ' + token } : {})
      },
      body: options.body ? JSON.stringify(options.body) : undefined
    })
  } catch (e) {
    throw new Error('无法连接后端服务，请确认服务已启动')
  }
  const data = await res.json().catch(() => ({}))
  if (!res.ok) {
    if (res.status === 401) onUnauthorized(scope)
    throw new Error(data.message || `请求失败 (${res.status})`)
  }
  return data
}

/** 上传单个文件（multipart/form-data，仅后台使用） */
async function upload(path, file) {
  const scope = SCOPES.admin
  const token = localStorage.getItem(scope.token)
  const form = new FormData()
  form.append('file', file)
  let res
  try {
    res = await fetch(BASE_URL + path, {
      method: 'POST',
      headers: token ? { Authorization: 'Bearer ' + token } : {},
      body: form
    })
  } catch (e) {
    throw new Error('无法连接后端服务，请确认服务已启动')
  }
  const data = await res.json().catch(() => ({}))
  if (!res.ok) {
    if (res.status === 401) onUnauthorized(scope)
    throw new Error(data.message || `请求失败 (${res.status})`)
  }
  return data
}

// ---------------- 鉴权 ----------------
export const authApi = {
  login: (payload) => request('/auth/login', { method: 'POST', body: payload }),
  register: (payload) => request('/auth/register', { method: 'POST', body: payload })
}

// ---------------- 行情 ----------------
export const marketApi = {
  getSnapshot: () => request('/market/snapshot')
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

// ---------------- 投资偏好（多套） ----------------
export const prefsApi = {
  list: () => request('/prefs'),
  create: (payload) => request('/prefs', { method: 'POST', body: payload }),
  update: (id, payload) => request('/prefs/' + id, { method: 'PUT', body: payload }),
  remove: (id) => request('/prefs/' + id, { method: 'DELETE' }),
  setDefault: (id) => request('/prefs/' + id + '/default', { method: 'POST' })
}

// ---------------- 全局设置（与偏好无关） ----------------
export const settingsApi = {
  get: () => request('/settings'),
  save: (payload) => request('/settings', { method: 'POST', body: payload })
}

// ---------------- 智能体 ----------------
/**
 * 非流式请求：一次性拿到完整结果，返回取消函数（AbortController）
 * @param {string} path - 相对 BASE_URL 的接口路径
 * @param {Object} body - 请求体
 * @param {Object} handlers - { onData(data), onError(err) }
 * @returns {Function} 取消函数
 */
function postOnce(path, body, { onData, onError } = {}) {
  const token = localStorage.getItem('quant_token')
  const controller = new AbortController()

  ;(async () => {
    let res
    try {
      res = await fetch(BASE_URL + path, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: 'Bearer ' + token } : {})
        },
        body: JSON.stringify(body),
        signal: controller.signal
      })
    } catch (e) {
      if (e.name === 'AbortError') return
      onError?.(new Error('无法连接后端服务，请确认服务已启动'))
      return
    }
    const data = await res.json().catch(() => ({}))
    if (!res.ok) {
      if (res.status === 401) {
        localStorage.removeItem('quant_token')
        localStorage.removeItem('quant_user')
        location.href = '/login'
      }
      onError?.(new Error(data.message || `请求失败 (${res.status})`))
      return
    }
    onData?.(data)
  })()

  return () => controller.abort()
}

export const agentApi = {
  /**
   * 策略生成智能体（非流式对话）
   * @param {Array} messages - 对话历史 [{role: 'user'|'assistant', content: '...'}, ...]
   * @param {Object} h - 结果回调
   * @param {Function} h.onText - 说明文本 (text) => void
   * @param {Function} h.onRag - 知识库检索命中 ({count, sources}) => void
   * @param {Function} h.onStrategy - 策略生成 (strategy) => void
   * @param {Function} h.onDone - 结束 () => void
   * @param {Function} h.onError - 错误 (err) => void
   * @returns {Function} 取消函数
   */
  chatStream(messages, h = {}) {
    return postOnce('/agent/generate-strategy', { messages }, {
      onData(data) {
        if (data.rag?.count) h.onRag?.(data.rag)
        if (data.text) h.onText?.(data.text)
        if (data.strategy) h.onStrategy?.(data.strategy)
        h.onDone?.()
      },
      onError: (e) => h.onError?.(e)
    })
  },

  /**
   * 自动荐股智能体（非流式分析）
   * @param {number|null} prefsId - 使用的偏好集 id，缺省后端用默认偏好
   * @param {Object} h - 结果回调
   * @param {Function} h.onText - 分析说明 (text) => void
   * @param {Function} h.onRecommend - 荐股结果 (list) => void
   * @param {Function} h.onDone - 结束 () => void
   * @param {Function} h.onError - 错误 (err) => void
   * @returns {Function} 取消函数
   */
  recommendStream(prefsId, h = {}) {
    return postOnce('/agent/recommend', { prefsId: prefsId || null }, {
      onData(data) {
        if (data.text) h.onText?.(data.text)
        if (data.recommend && data.recommend.length) h.onRecommend?.(data.recommend)
        h.onDone?.()
      },
      onError: (e) => h.onError?.(e)
    })
  }
}

// ---------------- 自选股 ----------------
export const watchlistApi = {
  list: () => request('/watchlist'),
  add: (code) => request('/watchlist', { method: 'POST', body: { code } }),
  remove: (code) => request('/watchlist/' + code, { method: 'DELETE' })
}

// ---------------- 策略 / 回测 ----------------
export const strategyApi = {
  frameworks: () => request('/strategy/frameworks'),
  saved: () => request('/strategy/saved'),
  save: (payload) => request('/strategy/saved', { method: 'POST', body: payload }),
  remove: (id) => request('/strategy/saved/' + id, { method: 'DELETE' })
}

export const runBacktest = (payload) => request('/strategy/backtest', { method: 'POST', body: payload })

// ---------------- 账户 ----------------
export const accountApi = {
  list: () => request('/accounts'),
  update: (id, patch) => request('/accounts/' + id, { method: 'PUT', body: patch }),
  create: (payload) => request('/accounts', { method: 'POST', body: payload }),
  remove: (id) => request('/accounts/' + id, { method: 'DELETE' })
}

// ---------------- 后台管理（知识库 + 用户） ----------------
export const adminApi = {
  login: (payload) => request('/admin/login', { method: 'POST', body: payload, scope: 'admin' }),
  stats: () => request('/admin/kb/stats', { scope: 'admin' }),
  docs: () => request('/admin/docs', { scope: 'admin' }),
  upload: (file) => upload('/admin/docs', file),
  removeDoc: (id) => request('/admin/docs/' + id, { method: 'DELETE', scope: 'admin' }),
  search: (payload) => request('/admin/search', { method: 'POST', body: payload, scope: 'admin' }),

  users: () => request('/admin/users', { scope: 'admin' }),
  createUser: (payload) => request('/admin/users', { method: 'POST', body: payload, scope: 'admin' }),
  updateUser: (id, payload) => request('/admin/users/' + id, { method: 'PUT', body: payload, scope: 'admin' }),
  removeUser: (id) => request('/admin/users/' + id, { method: 'DELETE', scope: 'admin' }),

  ragConfig: () => request('/admin/rag-config', { scope: 'admin' }),
  saveRagConfig: (payload) => request('/admin/rag-config', { method: 'PUT', body: payload, scope: 'admin' })
}