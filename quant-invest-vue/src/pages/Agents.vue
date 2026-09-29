<script setup>
import { ref } from 'vue'
import Icon from '../components/Icon.vue'
import RecommendAgent from '../components/RecommendAgent.vue'
import StrategyAgent from '../components/StrategyAgent.vue'

const tab = ref('recommend')
</script>

<template>
  <div>
    <div class="agent-tabs">
      <button :class="['agent-tab', tab === 'recommend' && 'active']" @click="tab = 'recommend'">
        <span class="agent-tab-icon teal">
          <Icon name="chart" :size="20" />
        </span>
        <div class="agent-tab-text">
          <strong>智能荐股</strong>
          <small>基于偏好的全市场 AI 扫描与评分</small>
        </div>
        <Icon v-if="tab === 'recommend'" name="check" :size="16" class="agent-tab-check" />
      </button>
      <button :class="['agent-tab', tab === 'strategy' && 'active']" @click="tab = 'strategy'">
        <span class="agent-tab-icon purple">
          <Icon name="robot" :size="20" />
        </span>
        <div class="agent-tab-text">
          <strong>策略生成</strong>
          <small>自然语言描述 → 可回测量化策略</small>
        </div>
        <Icon v-if="tab === 'strategy'" name="check" :size="16" class="agent-tab-check" />
      </button>
    </div>

    <RecommendAgent v-show="tab === 'recommend'" />
    <StrategyAgent v-show="tab === 'strategy'" />
  </div>
</template>

<style scoped>
.agent-tabs {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  margin-bottom: 16px;
}
.agent-tab {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 16px 18px;
  border-radius: var(--radius);
  border: 1px solid var(--border);
  background: var(--panel);
  transition: all 0.2s;
  text-align: left;
  width: 100%;
  position: relative;
  cursor: pointer;
}
.agent-tab:hover {
  border-color: var(--border-light);
  transform: translateY(-1px);
}
.agent-tab.active {
  border-color: var(--accent);
  background: linear-gradient(160deg, rgba(76, 141, 255, 0.1), rgba(56, 225, 255, 0.03));
  box-shadow: 0 0 0 1px var(--accent);
}
.agent-tab-icon {
  width: 44px;
  height: 44px;
  border-radius: 12px;
  display: grid;
  place-items: center;
  flex-shrink: 0;
}
.agent-tab-icon.teal {
  background: linear-gradient(135deg, #0ecb81, #38e1ff);
  color: #06231c;
}
.agent-tab-icon.purple {
  background: linear-gradient(135deg, var(--accent), var(--purple));
  color: #fff;
}
.agent-tab-text { flex: 1; }
.agent-tab-text strong { display: block; font-size: 15px; color: var(--text); }
.agent-tab-text small { display: block; color: var(--text-3); font-size: 12px; margin-top: 2px; }
.agent-tab-check { color: var(--accent-2); }

@media (max-width: 640px) {
  .agent-tabs { grid-template-columns: 1fr; }
}
</style>
