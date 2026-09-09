<script setup>
import RecommendAgent from '../components/RecommendAgent.vue'
import StrategyAgent from '../components/StrategyAgent.vue'
</script>

<template>
  <div>
    <div class="page-head">
      <div>
        <h1>AI 智能体中心</h1>
        <p>两大智能体协同工作：自动荐股发现机会，策略生成把想法变成可执行的量化策略</p>
      </div>
    </div>
    <RecommendAgent />
    <StrategyAgent />
  </div>
</template>