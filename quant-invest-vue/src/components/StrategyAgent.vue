<script setup>
import { ref, nextTick, watch, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { Card, Button, Badge, Chip } from './ui'
import Icon from './Icon.vue'
import { useAgentChat } from '../store/agent'

const QUICK_PROMPTS = [
  '你好，介绍一下你自己',
  '写一个 MACD 零轴上方金叉买入的策略',
  '帮我做一个沪深300成分股的动量轮动策略',
  '什么是量化交易？'
]

const router = useRouter()
// 聊天状态托管在 store，组件卸载不销毁，切回本页自动恢复
const { messages, input, typing, send, stopGenerate, saveStrategy } = useAgentChat()

const bodyRef = ref(null)

async function scrollDown() {
  await nextTick()
  bodyRef.value?.scrollTo({ top: bodyRef.value.scrollHeight, behavior: 'smooth' })
}
watch([messages, typing], scrollDown, { deep: true })
onMounted(scrollDown)
</script>

<template>
  <Card class="mt-16">
    <template #title>
      <span style="display: flex; align-items: center; gap: 9px">
        <span class="agent-avatar" style="width: 34px; height: 34px; border-radius: 9px">
          <Icon name="robot" :size="17" />
        </span>
        量化策略生成智能体
        <Badge tone="purple">QuantCopilot · 流式</Badge>
      </span>
    </template>

    <div class="chat-window">
      <div class="chat-messages" ref="bodyRef">
        <div v-for="(msg, i) in messages" :key="i" :class="['msg', msg.role]">
          <div class="msg-avatar">{{ msg.role === 'bot' ? 'AI' : '我' }}</div>
          <div class="msg-bubble">
            <!-- 文本内容 -->
            <div v-if="msg.text" style="white-space: pre-wrap">{{ msg.text }}<span v-if="msg.typing" class="cursor-blink">▍</span></div>

            <!-- 策略卡片 -->
            <div v-if="msg.strategy" class="strategy-card">
              <div style="font-weight: 700; margin-bottom: 8px">
                已生成策略：{{ msg.strategy.name }}
                <Badge tone="purple" style="margin-left: 8px">{{ msg.strategy.type }}</Badge>
              </div>
              <div style="font-size: 12.5px; color: var(--text-2)">交易规则：</div>
              <ul class="rule-list">
                <li v-for="(r, j) in msg.strategy.rules" :key="j">{{ r }}</li>
              </ul>
              <pre>{{ msg.strategy.code }}</pre>
              <div style="margin-top: 10px; display: flex; gap: 8px; align-items: center; flex-wrap: wrap">
                <Button v-if="!msg.saved" size="sm" icon="check" @click="saveStrategy(msg)">保存到我的量化策略</Button>
                <Badge v-else tone="up">已保存</Badge>
                <Button size="sm" icon="strategy" @click="router.push('/strategy')">前往回测验证</Button>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div class="quick-chips">
        <Chip v-for="p in QUICK_PROMPTS" :key="p" @click="send(p)">{{ p }}</Chip>
      </div>
      <div class="chat-input">
        <input
          class="input"
          :placeholder="typing ? 'AI 正在思考中…' : ''"
          v-model="input"
          @keydown.enter="send()"
          :disabled="typing"
        />
        <Button v-if="!typing" icon="send" @click="send()">发送</Button>
        <Button v-else variant="ghost" @click="stopGenerate">停止</Button>
      </div>
    </div>
  </Card>
</template>

<style scoped>
.cursor-blink {
  display: inline-block;
  margin-left: 2px;
  animation: blink 1s step-end infinite;
  color: var(--accent);
  font-weight: 400;
}
@keyframes blink {
  50% { opacity: 0; }
}
.strategy-card {
  margin-top: 12px;
  padding: 12px 14px;
  background: rgba(124, 58, 237, 0.08);
  border: 1px solid rgba(124, 58, 237, 0.25);
  border-radius: 10px;
}
</style>
