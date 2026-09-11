// 投资偏好相关静态选项（前端展示用常量，与后端数据约定保持一致）

export const SECTORS = ['白酒消费', '食品消费', '家电消费', '消费旅游', '银行金融', '券商金融', '保险金融', '新能源', '新能源车', '光伏新能源', '有色金属', '半导体', '人工智能', '电子科技', '通信运营', '医药生物', '公用事业']

export const RISK_LEVELS = ['保守型', '稳健型', '平衡型', '进取型', '激进型']

export const HORIZONS = ['短线（1个月内）', '中线（1-6个月）', '长线（1年以上）']

export const BENCHMARKS = ['沪深300', '上证指数', '中证500', '创业板指']

// 注意：默认值需与后端 quant-invest-server-py/data.py 的 DEFAULT_PREFS 保持一致，修改请同步两边
export const DEFAULT_PREFS = {
  risk: '稳健型',
  horizon: '中线（1-6个月）',
  sectors: ['新能源', '人工智能', '医药生物'],
  maxPosition: 25,
  stopLoss: 8,
  takeProfit: 30,
  tradeNotify: true,
  benchmark: '沪深300'
}