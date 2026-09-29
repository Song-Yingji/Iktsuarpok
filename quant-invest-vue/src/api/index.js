// ============================================================
// 前端 API 层：通过 HTTP 对接 Python/FastAPI 后端
// 后端地址可通过环境变量 VITE_API_BASE 覆盖，默认本地 3000 端口
// ============================================================
const BASE_URL = import.meta.env.VITE_API_BASE || 'http://localhost:3000/api'

async function request(path, options = {}) {
  const method = options.method || 'GET'
  const token = localStorage.getItem('quant_token')
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
    if (res.status === 401) {
      localStorage.removeItem('quant_token')
      localStorage.removeItem('quant_user')
      if (!['/login', '/register'].includes(location.pathname)) location.href = '/login'
    }
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
 * 打开一个 SSE 流并按事件分发（策略生成、智能荐股共用）
 * @param {string} path - 相对 BASE_URL 的接口路径
 * @param {Object} body - 请求体
 * @param {Object} handlers - { onEvent(evt), onError(err) }
 * @returns {Function} 取消函数
 */
function openStream(path, body, { onEvent, onError } = {}) {
  const token = localStorage.getItem('quant_token')
  const controller = new AbortController()

  fetch(BASE_URL + path, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: 'Bearer ' + token } : {})
    },
    body: JSON.stringify(body),
    signal: controller.signal
  }).then(async (res) => {
    if (!res.ok) {
      if (res.status === 401) {
        localStorage.removeItem('quant_token')
        localStorage.removeItem('quant_user')
        location.href = '/login'
      }
      throw new Error(`请求失败 (${res.status})`)
    }
    const reader = res.body.getReader()
    const decoder = new TextDecoder('utf-8')
    let buffer = ''

    while (true) {
      const { value, done } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })

      // SSE 以 \n\n 分隔事件
      let idx
      while ((idx = buffer.indexOf('\n\n')) !== -1) {
        const raw = buffer.slice(0, idx)
        buffer = buffer.slice(idx + 2)
        if (!raw.startsWith('data: ')) continue
        const jsonStr = raw.slice(6)
        if (!jsonStr.trim()) continue
        try {
          onEvent?.(JSON.parse(jsonStr))
        } catch (e) {
          // 忽略解析失败的行
        }
      }
    }
  }).catch((e) => {
    if (e.name === 'AbortError') return
    onError?.(e)
  })

  return () => controller.abort()
}

export const agentApi = {
  /**
   * 策略生成智能体（SSE 流式对话）
   * @param {Array} messages - 对话历史 [{role: 'user'|'assistant', content: '...'}, ...]
   * @param {Object} h - 事件回调
   * @param {Function} h.onText - 文本增量 (text) => void
   * @param {Function} h.onStrategy - 策略生成 (strategy) => void
   * @param {Function} h.onDone - 结束 () => void
   * @param {Function} h.onError - 错误 (err) => void
   * @returns {Function} 取消函数
   */
  chatStream(messages, h = {}) {
    return openStream('/agent/generate-strategy', { messages }, {
      onEvent(evt) {
        if (evt.type === 'text') h.onText?.(evt.data)
        else if (evt.type === 'strategy') h.onStrategy?.(evt.data)
        else if (evt.type === 'done') h.onDone?.()
      },
      onError: (e) => h.onError?.(e)
    })
  },

  /**
   * 自动荐股智能体（SSE 流式分析）
   * @param {number|null} prefsId - 使用的偏好集 id，缺省后端用默认偏好
   * @param {Object} h - 事件回调
   * @param {Function} h.onText - 分析说明增量 (text) => void
   * @param {Function} h.onRecommend - 荐股结果 (list) => void
   * @param {Function} h.onDone - 结束 () => void
   * @param {Function} h.onError - 错误 (err) => void
   * @returns {Function} 取消函数
   */
  recommendStream(prefsId, h = {}) {
    return openStream('/agent/recommend', { prefsId: prefsId || null }, {
      onEvent(evt) {
        if (evt.type === 'text') h.onText?.(evt.data)
        else if (evt.type === 'recommend') h.onRecommend?.(evt.data)
        else if (evt.type === 'done') h.onDone?.()
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