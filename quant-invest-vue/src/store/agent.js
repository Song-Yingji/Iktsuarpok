// ============================================================
// 智能体状态：集中托管在模块级 store
// 组件卸载只解绑视图，数据仍在，切换路由回来可直接恢复
// ============================================================
import { ref } from 'vue'
import { agentApi, prefsApi, strategyApi, watchlistApi } from '../api'
import { useApp } from './app'

const { toast } = useApp()

const GREETING = '你好，我是 Quant Buffett，你的量化投资伙伴。查行情、看基本面、刷财经新闻、管自选股，交给我就行；想弄懂某个投资概念，我会先翻自己的知识库再认真讲给你听；有投资想法直接说，我会像研究员一样「提假设→真实回测→复盘调整」，帮你打磨成能回测的策略。我不堆术语，有风险也会直说。'

// ---------------- 策略生成智能体 ----------------
const messages = ref([{ role: 'bot', text: GREETING, typing: false, greeting: true }])
const input = ref('')
const typing = ref(false)
// 当前展开检索浮层的消息下标。刻意放在 messages 之外：
// 若挂到消息对象上，切换展开状态会触发 scrollDown 的深度侦听，把对话框拉到底部
const ragOpenId = ref(null)
let cancelStream = null  // 非响应式：中断请求

function buildHistory() {
  // 策略消息转成摘要文本，避免空的 assistant 回复干扰模型
  return messages.value
    .filter((m) => !m.greeting && (m.role === 'user' || m.role === 'bot'))
    .map((m) => {
      if (m.strategy) {
        return { role: 'assistant', content: `已为用户生成量化策略：${m.strategy.name}（类型：${m.strategy.type}）` }
      }
      const text = (m.text || '').trim()
      if (!text) return null
      return { role: m.role === 'bot' ? 'assistant' : 'user', content: text }
    })
    .filter(Boolean)
}

function send(text) {
  const prompt = (text ?? input.value).trim()
  if (!prompt || typing.value) return
  input.value = ''
  typing.value = true
  ragOpenId.value = null  // 新的操作：收起上一轮的检索浮层

  messages.value.push({ role: 'user', text: prompt })

  // push 进数组的是原对象，直接改原对象不会触发视图更新，
  // 这里读回代理再写，保证文本、策略卡片与检索标记能实时渲染
  messages.value.push({ role: 'bot', text: '', typing: true, strategy: null, saved: false, rag: null, intent: null, trace: null })
  const botMsg = messages.value[messages.value.length - 1]

  cancelStream = agentApi.chatStream(buildHistory(), {
    onText(chunk) {
      botMsg.text += chunk
    },
    onIntent(intent) {
      botMsg.intent = intent
    },
    onTrace(trace) {
      botMsg.trace = trace
    },
    onRag(data) {
      // 只保留命中条数，用于气泡外的检索标记；具体命中哪些文档不在前端展示
      if (data?.count) botMsg.rag = { count: data.count }
    },
    onStrategy(data) {
      botMsg.strategy = data
    },
    onDone() {
      botMsg.typing = false
      typing.value = false
      cancelStream = null
    },
    onError(err) {
      botMsg.text += `\n\n[出错了] ${err.message || err}`
      botMsg.typing = false
      typing.value = false
      cancelStream = null
    }
  })
}

function stopGenerate() {
  if (!cancelStream) return
  cancelStream()
  cancelStream = null
  const last = messages.value[messages.value.length - 1]
  if (last && last.typing) {
    last.typing = false
    last.text += '\n\n（已停止生成）'
  }
  typing.value = false
  ragOpenId.value = null
}

async function saveStrategy(msg) {
  if (!msg.strategy) return
  const created = await strategyApi.save(msg.strategy)
  msg.saved = true
  msg.savedId = created?.id ?? null
  toast('已保存到我的量化策略')
}

// 已保存的策略可能在「我的量化策略」页被删除，此时历史消息的保存标记要一并失效，
// 否则「保存到我的量化策略」按钮不再出现，无法重新保存
async function syncSavedFlags() {
  let list
  try {
    list = await strategyApi.saved()
  } catch {
    return
  }
  const ids = new Set(list.map((s) => s.id))
  for (const m of messages.value) {
    if (m.saved && !ids.has(m.savedId)) {
      m.saved = false
      m.savedId = null
    }
  }
}

// ---------------- 自动荐股智能体 ----------------
const REC_STEPS = ['扫描全市场', '技术面分析', '基本面筛选', 'AI 综合评分']

const recs = ref(null)
const recText = ref('')
const recRunning = ref(false)
const recStep = ref(-1)
const watchedCodes = ref(new Set())
const prefSets = ref([])
const prefId = ref(null)
let cancelRec = null   // 非响应式：中断请求
let recTimer = null    // 非响应式：步骤进度定时器

// 每次进入页面重新拉取偏好与自选，保证自选状态与偏好列表是最新的
function loadRecoDeps() {
  prefsApi.list()
    .then((list) => {
      prefSets.value = list
      // 选中的偏好已被删除、或首次进入时，回落到默认偏好
      if (!list.some((p) => p.id === prefId.value)) {
        const def = list.find((p) => p.isDefault) || list[0]
        prefId.value = def ? def.id : null
      }
    })
    .catch(() => {})
  watchlistApi.list().then((list) => (watchedCodes.value = new Set(list.map((s) => s.code)))).catch(() => {})
}

function finishRecommend() {
  if (recTimer) {
    clearInterval(recTimer)
    recTimer = null
  }
  cancelRec = null
  recRunning.value = false
  recStep.value = -1
}

function runRecommend() {
  if (recRunning.value) return

  recRunning.value = true
  recs.value = null
  recText.value = ''
  recStep.value = 0

  // 步骤条随时间推进，收到结果后停在最后一步
  recTimer = setInterval(() => {
    if (recStep.value < REC_STEPS.length - 1) recStep.value += 1
  }, 900)

  cancelRec = agentApi.recommendStream(prefId.value, {
    onText(chunk) {
      recText.value += chunk
      if (recStep.value < 1) recStep.value = 1
    },
    onRecommend(data) {
      recs.value = data
      recStep.value = REC_STEPS.length - 1
    },
    onDone() {
      finishRecommend()
      toast('荐股智能体已完成本轮分析')
    },
    onError(err) {
      recText.value += `\n\n[出错了] ${err.message || err}`
      finishRecommend()
    }
  })
}

function stopRecommend() {
  if (cancelRec) {
    cancelRec()
    cancelRec = null
  }
  if (recTimer) {
    clearInterval(recTimer)
    recTimer = null
  }
  recRunning.value = false
  recStep.value = -1
  if (recText.value && !recs.value) recText.value += '\n\n（已停止分析）'
}

async function addWatch(r) {
  await watchlistApi.add(r.code)
  watchedCodes.value = new Set([...watchedCodes.value, r.code])
  toast(`已将 ${r.name} 加入自选股`)
}

// 退出登录时清空，避免下一个登录用户看到上一个人的对话与荐股结果
function resetAgentState() {
  if (cancelStream) {
    cancelStream()
    cancelStream = null
  }
  if (cancelRec) {
    cancelRec()
    cancelRec = null
  }
  if (recTimer) {
    clearInterval(recTimer)
    recTimer = null
  }
  messages.value = [{ role: 'bot', text: GREETING, typing: false, greeting: true }]
  input.value = ''
  typing.value = false
  ragOpenId.value = null
  recs.value = null
  recText.value = ''
  recRunning.value = false
  recStep.value = -1
  watchedCodes.value = new Set()
  prefSets.value = []
  prefId.value = null
}

export function useAgentChat() {
  return { messages, input, typing, ragOpenId, send, stopGenerate, saveStrategy, syncSavedFlags }
}

export function useRecommendAgent() {
  return {
    REC_STEPS, recs, recText, recRunning, recStep, watchedCodes, prefSets, prefId,
    loadRecoDeps, runRecommend, stopRecommend, addWatch
  }
}

export { resetAgentState }
