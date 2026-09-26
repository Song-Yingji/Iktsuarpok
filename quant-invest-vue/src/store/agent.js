// ============================================================
// 智能体状态：集中托管在模块级 store
// 组件卸载只解绑视图，数据仍在，切换路由回来可直接恢复
// ============================================================
import { ref } from 'vue'
import { agentApi, prefsApi, strategyApi, watchlistApi } from '../api'
import { useApp } from './app'

const { toast } = useApp()

const GREETING = '你好，我是策略生成智能体 QuantCopilot。你可以和我聊投资知识，也可以用自然语言描述投资想法（例如「MACD 金叉买入、放量突破」），我会生成可回测的量化策略。'

// ---------------- 策略生成智能体 ----------------
const messages = ref([{ role: 'bot', text: GREETING, typing: false, greeting: true }])
const input = ref('')
const typing = ref(false)
// 非响应式：仅用于中断流式请求，不参与渲染
let cancelStream = null

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

  messages.value.push({ role: 'user', text: prompt })

  // 占位的 bot 消息，流式填充
  const botMsg = { role: 'bot', text: '', typing: true, strategy: null, saved: false }
  messages.value.push(botMsg)

  cancelStream = agentApi.chatStream(buildHistory(), {
    onText(chunk) {
      botMsg.text += chunk
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
}

async function saveStrategy(msg) {
  if (!msg.strategy) return
  await strategyApi.save(msg.strategy)
  msg.saved = true
  toast('已保存到我的量化策略')
}

// ---------------- 自动荐股智能体 ----------------
const REC_STEPS = ['扫描全市场', '技术面分析', '基本面筛选', 'AI 综合评分']

const recs = ref(null)
const recRunning = ref(false)
const recStep = ref(-1)
const watchedCodes = ref(new Set())
let prefs = null

// 每次进入页面重新拉取偏好与自选，保证自选状态是最新的
function loadRecoDeps() {
  prefsApi.get().then((p) => (prefs = p)).catch(() => {})
  watchlistApi.list().then((list) => (watchedCodes.value = new Set(list.map((s) => s.code)))).catch(() => {})
}

async function runRecommend() {
  recRunning.value = true
  recs.value = null
  for (let i = 0; i < REC_STEPS.length; i++) {
    recStep.value = i
    await new Promise((r) => setTimeout(r, 550))
  }
  const data = await agentApi.recommend(prefs)
  recs.value = data
  recStep.value = -1
  recRunning.value = false
  toast('荐股智能体已完成本轮分析')
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
  messages.value = [{ role: 'bot', text: GREETING, typing: false, greeting: true }]
  input.value = ''
  typing.value = false
  recs.value = null
  recRunning.value = false
  recStep.value = -1
  watchedCodes.value = new Set()
  prefs = null
}

export function useAgentChat() {
  return { messages, input, typing, send, stopGenerate, saveStrategy }
}

export function useRecommendAgent() {
  return { REC_STEPS, recs, recRunning, recStep, watchedCodes, loadRecoDeps, runRecommend, addWatch }
}

export { resetAgentState }
