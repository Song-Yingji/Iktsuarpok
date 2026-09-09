// 数字与文本格式化工具
export const fmt = {
  num: (n, d = 2) =>
    n == null || isNaN(n)
      ? '--'
      : Number(n).toLocaleString('zh-CN', { minimumFractionDigits: d, maximumFractionDigits: d }),
  price: (n) => (n == null ? '--' : Number(n).toFixed(2)),
  // 带符号百分比，如 +1.28%
  pct: (n, d = 2) => (n == null ? '--' : (n >= 0 ? '+' : '') + (n * 100).toFixed(d) + '%'),
  pctPlain: (n, d = 2) => (n == null ? '--' : (n * 100).toFixed(d) + '%'),
  money: (n) => '¥' + Math.round(n).toLocaleString('zh-CN'),
  moneyWan: (n) => {
    const abs = Math.abs(n)
    if (abs >= 1e8) return (n / 1e8).toFixed(2) + ' 亿'
    if (abs >= 1e4) return (n / 1e4).toFixed(1) + ' 万'
    return n.toFixed(0)
  },
  vol: (n) => {
    if (n >= 1e8) return (n / 1e8).toFixed(2) + '亿'
    if (n >= 1e4) return (n / 1e4).toFixed(1) + '万'
    return n.toFixed(0)
  }
}

// A股惯例：红涨绿跌
export const tone = (n) => (n > 0 ? 'up' : n < 0 ? 'down' : 'flat')
export const toneColor = (n) => (n > 0 ? 'var(--up)' : n < 0 ? 'var(--down)' : 'var(--text-2)')

// 确定性伪随机数生成器（同一代码生成稳定的历史K线）
export function hashSeed(str) {
  let h = 1779033703 ^ str.length
  for (let i = 0; i < str.length; i++) {
    h = Math.imul(h ^ str.charCodeAt(i), 3432918353)
    h = (h << 13) | (h >>> 19)
  }
  return function () {
    h = Math.imul(h ^ (h >>> 16), 2246822507)
    h = Math.imul(h ^ (h >>> 13), 3266489909)
    h ^= h >>> 16
    return (h >>> 0) / 4294967296
  }
}

// 生成交易日日期序列（跳过周末），返回到今天为止的 days 个日期
export function tradingDates(days) {
  const dates = []
  const d = new Date('2026-09-04T15:00:00')
  while (dates.length < days) {
    const day = d.getDay()
    if (day !== 0 && day !== 6) {
      dates.unshift(
        `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
      )
    }
    d.setDate(d.getDate() - 1)
  }
  return dates
}

export const delay = (ms) => new Promise((r) => setTimeout(r, ms))

export function cls(...parts) {
  return parts.filter(Boolean).join(' ')
}
