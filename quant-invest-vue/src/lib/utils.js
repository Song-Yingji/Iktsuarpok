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