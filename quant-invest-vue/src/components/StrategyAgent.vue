<script setup>
import { ref, nextTick, watch } from 'vue'
import { useRouter } from 'vue-router'
import { agentApi, strategyApi } from '../api'
import { Card, Button, Badge, Chip } from './ui'
import Icon from './Icon.vue'
import { useApp } from '../store/app'

const QUICK_PROMPTS = [
  '写一个 MACD 零轴上方金叉买入的策略',
  '帮我做一个沪深300成分股的动量轮动策略',
  '写一个5日均线和20日均线金叉的双均线策略'
]

const router = useRouter()
const { toast } = useApp()
const messages = ref([
  {
    role: 'bot',
    text: '你好，我是策略生成智能体 QuantCopilot。你可以用自然语言描述投资想法，例如「MACD 金叉买入、放量突破」，我会自动生成可回测的量化策略规则与代码。'
  }
])
const input = ref('')
const typing = ref(false)
const bodyRef = ref(null)

async function scrollDown() {
  await nextTick()
  bodyRef.value?.scrollTo({ top: bodyRef.value.scrollHeight, behavior: 'smooth' })
}
watch([messages, typing], scrollDown, { deep: true })

async function send(text) {
  const prompt = (text ?? input.value).trim()
  if (!prompt || typing.value) return
  input.value = ''
  messages.value.push({ role: 'user', text: prompt })
  typing.value = true
  const res = await agentApi.generateStrategy(prompt)
  typing.value = false
  messages.value.push({ role: 'bot', type: 'strategy', data: res })
}

async function saveStrategy(msg) {
  await strategyApi.save(msg.data)
  msg.saved = true
  toast('已保存到我的量化策略')
}
</script>

<template>
  <Card class="mt-16">
    <template #title>
      <span style="display: flex; align-items: center; gap: 9px">
        <span class="agent-avatar" style="width: 34px; height: 34px; border-radius: 9px">
          <Icon name="robot" :size="17" />
        </span>
        量化策略生成智能体
        <Badge tone="purple">QuantCopilot v1.8</Badge>
      </span>
    </template>

    <div class="chat-window">
      <div class="chat-messages" ref="bodyRef">
        <div v-for="(msg, i) in messages" :key="i" :class="['msg', msg.role]">
          <div class="msg-avatar">{{ msg.role === 'bot' ? 'AI' : '我' }}</div>
          <div class="msg-bubble">
            <div v-if="msg.text">{{ msg.text }}</div>
            <div v-if="msg.type === 'strategy'">
              <div style="font-weight: 700; margin-bottom: 8px">
                已生成策略：{{ msg.data.name }}
                <Badge tone="purple" style="margin-left: 8px">{{ msg.data.type }}</Badge>
              </div>
              <div style="font-size: 12.5px; color: var(--text-2)">交易规则：</div>
              <ul class="rule-list">
                <li v-for="(r, j) in msg.data.rules" :key="j">{{ r }}</li>
              </ul>
              <pre>{{ msg.data.code }}</pre>
              <div style="margin-top: 10px; display: flex; gap: 8px; align-items: center">
                <Button v-if="!msg.saved" size="sm" icon="check" @click="saveStrategy(msg)">保存到我的量化策略</Button>
                <Badge v-else tone="up">已保存</Badge>
                <Button size="sm" icon="strategy" @click="router.push('/strategy')">前往回测验证</Button>
              </div>
            </div>
          </div>
        </div>
        <div v-if="typing" class="msg bot">
          <div class="msg-avatar">AI</div>
          <div class="msg-bubble" style="color: var(--text-3)">正在理解你的投资逻辑并生成策略…</div>
        </div>
      </div>

      <div class="quick-chips">
        <Chip v-for="p in QUICK_PROMPTS" :key="p" @click="send(p)">{{ p }}</Chip>
      </div>
      <div class="chat-input">
        <input
          class="input"
          placeholder="描述你的策略想法，例如：均线金叉买入、跌破20日线止损…"
          v-model="input"
          @keydown.enter="send()"
        />
        <Button icon="send" @click="send()">发送</Button>
      </div>
    </div>
  </Card>
</template>