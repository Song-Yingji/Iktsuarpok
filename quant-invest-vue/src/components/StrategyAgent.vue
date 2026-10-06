<script setup>
import { ref, nextTick, watch, onMounted, onBeforeUnmount } from 'vue'
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
const { messages, input, typing, ragOpenId, send, stopGenerate, saveStrategy, syncSavedFlags } = useAgentChat()

const bodyRef = ref(null)

async function scrollDown() {
  await nextTick()
  bodyRef.value?.scrollTo({ top: bodyRef.value.scrollHeight, behavior: 'smooth' })
}
watch([messages, typing], scrollDown, { deep: true })

// 检索浮层：同一时刻只展开一个，点击图标切换
function toggleRag(i) {
  ragOpenId.value = ragOpenId.value === i ? null : i
}
// 点击页面空白处自动收起
function closeRag() {
  ragOpenId.value = null
}

onMounted(() => {
  scrollDown()
  syncSavedFlags()
  document.addEventListener('click', closeRag)
})
onBeforeUnmount(() => {
  document.removeEventListener('click', closeRag)
  ragOpenId.value = null
})
</script>

<template>
  <Card>
    <template #title>
      <span style="display: flex; align-items: center; gap: 9px">
        <span class="agent-avatar" style="width: 34px; height: 34px; border-radius: 9px">
          <Icon name="robot" :size="17" />
        </span>
        量化策略生成智能体
        <Badge tone="purple">Quant Buffett</Badge>
      </span>
    </template>

    <div class="chat-window">
      <div class="chat-messages" ref="bodyRef">
        <div v-for="(msg, i) in messages" :key="i" :class="['msg', msg.role]">
          <div class="msg-avatar">{{ msg.role === 'bot' ? 'AI' : '我' }}</div>
          <div class="msg-bubble">
            <div v-if="msg.text" style="white-space: pre-wrap">{{ msg.text }}<span v-if="msg.typing" class="cursor-blink">▍</span></div>

            <div v-if="msg.strategy" class="strategy-card">
              <div class="strat-card-head">
                <div class="strat-card-title">
                  <Icon name="strategy" :size="16" />
                  <span>{{ msg.strategy.name }}</span>
                </div>
                <Badge tone="purple">{{ msg.strategy.type }}</Badge>
              </div>
              <div class="strat-card-rules">
                <span class="strat-rules-label">交易规则</span>
                <ul class="rule-list">
                  <li v-for="(r, j) in msg.strategy.rules" :key="j">{{ r }}</li>
                </ul>
              </div>
              <pre>{{ msg.strategy.code }}</pre>
              <div class="strat-card-actions">
                <Button v-if="!msg.saved" size="sm" icon="check" @click="saveStrategy(msg)">保存到我的量化策略</Button>
                <Badge v-else tone="up">已保存</Badge>
                <Button size="sm" icon="strategy" @click="router.push('/strategy')">前往回测验证</Button>
              </div>
            </div>
          </div>

          <div v-if="msg.role === 'bot' && msg.rag" class="rag-mark">
            <button
              type="button"
              :class="['rag-mark-btn', ragOpenId === i && 'active']"
              title="查看知识库检索信息"
              @click.stop="toggleRag(i)"
            >
              <Icon name="db" :size="13" />
            </button>
            <transition name="rag-pop">
              <div v-if="ragOpenId === i" class="rag-mark-pop" @click.stop>
                已检索本地知识库，命中 {{ msg.rag.count }} 条参考片段
              </div>
            </transition>
          </div>
        </div>
      </div>

      <div class="quick-chips">
        <span class="quick-label">快速提问</span>
        <Chip v-for="p in QUICK_PROMPTS" :key="p" @click="send(p)" class="quick-chip">{{ p }}</Chip>
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
  padding: 14px;
  background: rgba(124, 58, 237, 0.06);
  border: 1px solid rgba(124, 58, 237, 0.22);
  border-radius: 12px;
}
.strat-card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}
.strat-card-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 700;
  font-size: 14px;
  color: var(--purple);
}
.strat-card-rules { margin-bottom: 8px; }
.strat-rules-label {
  font-size: 12px;
  color: var(--text-3);
  display: block;
  margin-bottom: 4px;
}
.strat-card-actions {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
  margin-top: 12px;
}
.quick-label {
  font-size: 12px;
  color: var(--text-3);
  align-self: center;
  margin-right: 2px;
}
.quick-chip::before {
  content: '›';
  color: var(--accent-2);
  font-weight: 700;
  margin-right: 4px;
}

/* 为右侧单行检索浮层预留空间，避免浮层与气泡重叠 */
.msg.bot {
  max-width: 64%;
}

/* 气泡外右下角的检索标记：底部与气泡齐平 */
.rag-mark {
  position: relative;
  align-self: flex-end;
  flex-shrink: 0;
  display: flex;
  align-items: flex-end;
}
.rag-mark-btn {
  width: 22px;
  height: 22px;
  display: grid;
  place-items: center;
  padding: 0;
  border-radius: 7px;
  background: transparent;
  border: 1px solid transparent;
  color: var(--text-3);
  cursor: pointer;
  transition: color 0.15s, background 0.15s, border-color 0.15s;
}
.rag-mark-btn:hover {
  color: var(--accent-2);
  background: var(--panel-2);
  border-color: var(--border);
}
.rag-mark-btn.active {
  color: var(--accent-2);
  background: rgba(56, 225, 255, 0.08);
  border-color: rgba(56, 225, 255, 0.3);
}
/* 浮层在图标右侧单行展开，底边与图标（即气泡底边）齐平 */
.rag-mark-pop {
  position: absolute;
  left: calc(100% + 6px);
  bottom: 0;
  white-space: nowrap;
  padding: 7px 11px;
  border-radius: 9px;
  font-size: 11.5px;
  line-height: 1.5;
  color: var(--text-2);
  background: #0d1526;
  border: 1px solid var(--border);
  box-shadow: 0 8px 22px rgba(0, 0, 0, 0.4);
  z-index: 6;
}
.rag-pop-enter-active,
.rag-pop-leave-active {
  transition: opacity 0.16s ease, transform 0.16s ease;
}
.rag-pop-enter-from,
.rag-pop-leave-to {
  opacity: 0;
  transform: translateX(-4px);
}
</style>
