// ============================================================
// 自由构建（Strategy Builder）图 DSL 前端定义
// 与后端 builder_engine.NODE_DEFS 保持一致：节点类型 / 端口 / 参数规格
// 端口类型只有 series（数值序列）与 bool（布尔信号）两种
// ============================================================

export const NODE_DEFS = {
  close: { label: '收盘价', group: 'source', inputs: {}, outputs: { value: 'series' }, params: {} },
  high: { label: '最高价', group: 'source', inputs: {}, outputs: { value: 'series' }, params: {} },
  low: { label: '最低价', group: 'source', inputs: {}, outputs: { value: 'series' }, params: {} },
  volume: { label: '成交量', group: 'source', inputs: {}, outputs: { value: 'series' }, params: {} },
  const: {
    label: '常量', group: 'source', inputs: {}, outputs: { value: 'series' },
    params: { value: { label: '数值', kind: 'float', default: 0, min: -1e9, max: 1e9 } }
  },

  ma: {
    label: 'MA 均线', group: 'indicator', inputs: { source: 'series' }, outputs: { value: 'series' },
    params: { period: { label: '周期', kind: 'int', default: 5, min: 2, max: 250 } }
  },
  ema: {
    label: 'EMA 均线', group: 'indicator', inputs: { source: 'series' }, outputs: { value: 'series' },
    params: { period: { label: '周期', kind: 'int', default: 12, min: 2, max: 250 } }
  },
  rsi: {
    label: 'RSI', group: 'indicator', inputs: { source: 'series' }, outputs: { value: 'series' },
    params: { period: { label: '周期', kind: 'int', default: 14, min: 2, max: 250 } }
  },
  macd: {
    label: 'MACD', group: 'indicator', inputs: { source: 'series' }, outputs: { dif: 'series', dea: 'series' },
    params: {
      fast: { label: '快线周期', kind: 'int', default: 12, min: 2, max: 100 },
      slow: { label: '慢线周期', kind: 'int', default: 26, min: 2, max: 200 },
      signal: { label: '信号线周期', kind: 'int', default: 9, min: 2, max: 100 }
    }
  },
  boll: {
    label: 'BOLL 布林带', group: 'indicator', inputs: { source: 'series' },
    outputs: { upper: 'series', mid: 'series', lower: 'series' },
    params: {
      period: { label: '周期', kind: 'int', default: 20, min: 2, max: 250 },
      mult: { label: '标准差倍数', kind: 'float', default: 2, min: 0.5, max: 5 }
    }
  },

  cross_up: { label: '上穿（金叉）', group: 'condition', inputs: { a: 'series', b: 'series' }, outputs: { value: 'bool' }, params: {} },
  cross_down: { label: '下穿（死叉）', group: 'condition', inputs: { a: 'series', b: 'series' }, outputs: { value: 'bool' }, params: {} },
  gt: { label: '大于', group: 'condition', inputs: { a: 'series', b: 'series' }, outputs: { value: 'bool' }, params: {} },
  lt: { label: '小于', group: 'condition', inputs: { a: 'series', b: 'series' }, outputs: { value: 'bool' }, params: {} },

  and: { label: '且 AND', group: 'logic', inputs: { a: 'bool', b: 'bool' }, outputs: { value: 'bool' }, params: {} },
  or: { label: '或 OR', group: 'logic', inputs: { a: 'bool', b: 'bool' }, outputs: { value: 'bool' }, params: {} },
  not: { label: '非 NOT', group: 'logic', inputs: { a: 'bool' }, outputs: { value: 'bool' }, params: {} },

  buy: { label: '买入信号', group: 'action', inputs: { signal: 'bool' }, outputs: {}, params: {} },
  sell: { label: '卖出信号', group: 'action', inputs: { signal: 'bool' }, outputs: {}, params: {} }
}

export const GROUPS = [
  { id: 'source', label: '数据源', color: '#38e1ff' },
  { id: 'indicator', label: '技术指标', color: '#4c8dff' },
  { id: 'condition', label: '条件判断', color: '#f0b90b' },
  { id: 'logic', label: '逻辑组合', color: '#a66bff' },
  { id: 'action', label: '交易动作', color: '#f6465d' }
]

export const PORT_LABELS = {
  source: '数据', a: 'A', b: 'B', signal: '信号',
  value: '值', dif: 'DIF', dea: 'DEA', upper: '上轨', mid: '中轨', lower: '下轨'
}

export function nodeColor(type) {
  if (type === 'buy') return '#f6465d'
  if (type === 'sell') return '#0ecb81'
  return GROUPS.find((g) => g.id === NODE_DEFS[type]?.group)?.color || '#4c8dff'
}

export function edgeColor(portType) {
  return portType === 'bool' ? '#a66bff' : '#4c8dff'
}

export function paramSummary(type, params = {}) {
  if (type === 'ma' || type === 'ema' || type === 'rsi') return `周期 ${params.period}`
  if (type === 'macd') return `${params.fast} / ${params.slow} / ${params.signal}`
  if (type === 'boll') return `周期 ${params.period} · ${params.mult} 倍标准差`
  if (type === 'const') return `数值 = ${params.value}`
  return ''
}

let seq = 0
export function createNode(type, position) {
  const params = {}
  for (const [key, spec] of Object.entries(NODE_DEFS[type].params)) params[key] = spec.default
  return {
    id: `n${Date.now().toString(36)}_${seq++}`,
    type,
    position,
    data: { params, error: null }
  }
}

// ---------------- 内置模板 ----------------
const nd = (id, type, x, y, params = {}) => ({ id, type, params, position: { x, y } })
const eg = (source, sourcePort, target, targetPort) => ({
  id: `${source}.${sourcePort}->${target}.${targetPort}`, source, sourcePort, target, targetPort
})

export const TEMPLATES = [
  {
    id: 'ma_cross',
    name: '双均线趋势',
    desc: 'MA5 上穿 MA20 金叉买入，下穿死叉卖出，与内置双均线引擎完全等价',
    graph: {
      version: 1,
      nodes: [
        nd('c', 'close', 0, 150), nd('f', 'ma', 250, 60, { period: 5 }), nd('s', 'ma', 250, 240, { period: 20 }),
        nd('cu', 'cross_up', 520, 60), nd('cd', 'cross_down', 520, 240),
        nd('b', 'buy', 790, 60), nd('sl', 'sell', 790, 240)
      ],
      edges: [
        eg('c', 'value', 'f', 'source'), eg('c', 'value', 's', 'source'),
        eg('f', 'value', 'cu', 'a'), eg('s', 'value', 'cu', 'b'),
        eg('f', 'value', 'cd', 'a'), eg('s', 'value', 'cd', 'b'),
        eg('cu', 'value', 'b', 'signal'), eg('cd', 'value', 'sl', 'signal')
      ]
    }
  },
  {
    id: 'macd_zero',
    name: 'MACD 零轴上金叉',
    desc: 'DIF 上穿 DEA 且 DIF 在零轴上方时买入，DIF 下穿 DEA 卖出',
    graph: {
      version: 1,
      nodes: [
        nd('c', 'close', 0, 170), nd('m', 'macd', 250, 170), nd('z', 'const', 250, 360, { value: 0 }),
        nd('cu', 'cross_up', 540, 60), nd('gt', 'gt', 540, 230), nd('and', 'and', 800, 130),
        nd('cd', 'cross_down', 540, 400), nd('b', 'buy', 1050, 130), nd('sl', 'sell', 1050, 400)
      ],
      edges: [
        eg('c', 'value', 'm', 'source'),
        eg('m', 'dif', 'cu', 'a'), eg('m', 'dea', 'cu', 'b'),
        eg('m', 'dif', 'gt', 'a'), eg('z', 'value', 'gt', 'b'),
        eg('cu', 'value', 'and', 'a'), eg('gt', 'value', 'and', 'b'),
        eg('m', 'dif', 'cd', 'a'), eg('m', 'dea', 'cd', 'b'),
        eg('and', 'value', 'b', 'signal'), eg('cd', 'value', 'sl', 'signal')
      ]
    }
  },
  {
    id: 'rsi_reversal',
    name: 'RSI 超卖反转',
    desc: 'RSI 从下方上穿 30（超卖回升）买入，从上方下穿 70（超买回落）卖出',
    graph: {
      version: 1,
      nodes: [
        nd('c', 'close', 0, 170), nd('r', 'rsi', 250, 170, { period: 14 }),
        nd('h', 'const', 250, 20, { value: 70 }), nd('l', 'const', 250, 340, { value: 30 }),
        nd('cd', 'cross_down', 540, 60), nd('cu', 'cross_up', 540, 260),
        nd('sl', 'sell', 810, 60), nd('b', 'buy', 810, 260)
      ],
      edges: [
        eg('c', 'value', 'r', 'source'),
        eg('r', 'value', 'cu', 'a'), eg('l', 'value', 'cu', 'b'),
        eg('r', 'value', 'cd', 'a'), eg('h', 'value', 'cd', 'b'),
        eg('cu', 'value', 'b', 'signal'), eg('cd', 'value', 'sl', 'signal')
      ]
    }
  }
]

// ---------------- DSL ↔ 画布模型互转 ----------------
export function graphToFlow(graph) {
  const g = graph || {}
  const typeOf = {}
  const nodes = (g.nodes || []).map((n) => {
    typeOf[n.id] = n.type
    return {
      id: n.id,
      type: n.type,
      position: n.position || { x: 0, y: 0 },
      data: { params: { ...(n.params || {}) }, error: null }
    }
  })
  const edges = (g.edges || []).map((e, i) => {
    const portType = NODE_DEFS[typeOf[e.source]]?.outputs[e.sourcePort]
    return {
      id: e.id || `e${i}`,
      source: e.source,
      target: e.target,
      sourceHandle: e.sourcePort,
      targetHandle: e.targetPort,
      type: 'smoothstep',
      style: { stroke: edgeColor(portType), strokeWidth: 1.6 }
    }
  })
  return { nodes, edges }
}

export function flowToGraph(nodes, edges) {
  return {
    version: 1,
    nodes: nodes.map((n) => ({
      id: n.id,
      type: n.type,
      params: { ...(n.data?.params || {}) },
      position: { x: Math.round(n.position.x), y: Math.round(n.position.y) }
    })),
    edges: edges.map((e) => ({
      id: e.id,
      source: e.source,
      sourcePort: e.sourceHandle,
      target: e.target,
      targetPort: e.targetHandle
    }))
  }
}