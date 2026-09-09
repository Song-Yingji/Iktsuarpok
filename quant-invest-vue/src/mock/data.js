import { hashSeed, tradingDates } from '../lib/utils'

// ============ 大盘指数 ============
export const INDICES = [
  { code: 'SH000001', name: '上证指数', base: 3128.45 },
  { code: 'SZ399001', name: '深证成指', base: 9862.13 },
  { code: 'SZ399006', name: '创业板指', base: 1932.76 },
  { code: 'SH000300', name: '沪深300', base: 3685.22 },
  { code: 'SH000688', name: '科创50', base: 882.47 }
]

// ============ 个股 ============
// name, sector 行业板块, base 基准价(今开附近), pe 市盈率
export const STOCKS = [
  { code: '600519', name: '贵州茅台', sector: '白酒消费', base: 1685.0, pe: 24.5 },
  { code: '000858', name: '五粮液', sector: '白酒消费', base: 142.3, pe: 18.2 },
  { code: '603288', name: '海天味业', sector: '食品消费', base: 38.64, pe: 35.2 },
  { code: '600887', name: '伊利股份', sector: '食品消费', base: 26.35, pe: 16.8 },
  { code: '000333', name: '美的集团', sector: '家电消费', base: 68.92, pe: 13.4 },
  { code: '601888', name: '中国中免', sector: '消费旅游', base: 68.15, pe: 24.6 },
  { code: '601318', name: '中国平安', sector: '保险金融', base: 48.65, pe: 8.6 },
  { code: '600036', name: '招商银行', sector: '银行金融', base: 35.42, pe: 6.2 },
  { code: '000001', name: '平安银行', sector: '银行金融', base: 11.28, pe: 4.8 },
  { code: '601988', name: '中国银行', sector: '银行金融', base: 4.62, pe: 6.0 },
  { code: '600030', name: '中信证券', sector: '券商金融', base: 22.86, pe: 14.3 },
  { code: '300059', name: '东方财富', sector: '券商金融', base: 15.63, pe: 28.4 },
  { code: '300750', name: '宁德时代', sector: '新能源', base: 198.75, pe: 22.1 },
  { code: '002594', name: '比亚迪', sector: '新能源车', base: 245.6, pe: 20.8 },
  { code: '601012', name: '隆基绿能', sector: '光伏新能源', base: 18.42, pe: 12.5 },
  { code: '601899', name: '紫金矿业', sector: '有色金属', base: 17.56, pe: 12.1 },
  { code: '688981', name: '中芯国际', sector: '半导体', base: 88.34, pe: 45.6 },
  { code: '000725', name: '京东方A', sector: '电子科技', base: 4.18, pe: 22.7 },
  { code: '002415', name: '海康威视', sector: '人工智能', base: 32.18, pe: 19.7 },
  { code: '002230', name: '科大讯飞', sector: '人工智能', base: 45.26, pe: 72.3 },
  { code: '600050', name: '中国联通', sector: '通信运营', base: 5.46, pe: 16.2 },
  { code: '600276', name: '恒瑞医药', sector: '医药生物', base: 46.85, pe: 38.9 },
  { code: '300760', name: '迈瑞医疗', sector: '医药生物', base: 268.4, pe: 26.3 },
  { code: '600900', name: '长江电力', sector: '公用事业', base: 27.83, pe: 19.5 }
]

// 生成确定性历史K线：{ date, open, close, high, low, volume }
function genCandles(code, base, days = 240) {
  const rnd = hashSeed('kline-' + code)
  const dates = tradingDates(days)
  const drift = (rnd() - 0.46) * 0.0018
  const vol = 0.011 + rnd() * 0.016
  const raw = []
  let price = base * (0.62 + rnd() * 0.5)
  for (let i = 0; i < days; i++) {
    const open = price
    const close = open * (1 + drift + (rnd() - 0.5) * vol * 2)
    const high = Math.max(open, close) * (1 + rnd() * vol * 0.7)
    const low = Math.min(open, close) * (1 - rnd() * vol * 0.7)
    const volume = Math.round((0.5 + rnd() * 1.4) * 8e6)
    raw.push({ date: dates[i], open, close, high, low, volume })
    price = close
  }
  // 缩放使最后一根K线收盘价 = base
  const scale = base / raw[raw.length - 1].close
  raw.forEach((c) => {
    c.open *= scale
    c.close *= scale
    c.high *= scale
    c.low *= scale
  })
  return raw
}

// ============ 行情引擎（单例，模拟实时推送） ============
let market = null

export function getMarket() {
  if (market) return market
  const stocks = STOCKS.map((s) => {
    const history = genCandles(s.code, s.base)
    const today = history[history.length - 1]
    const prevClose = history[history.length - 2].close
    const rnd = hashSeed('meta-' + s.code)
    return {
      ...s,
      history,
      prevClose,
      open: today.open,
      price: today.close,
      lastPrice: today.close, // 上一tick价格，用于闪烁动画
      high: today.high,
      low: today.low,
      volume: today.volume,
      amount: today.volume * today.close,
      turnover: (0.4 + rnd() * 3.2), // 换手率 %
      spark: history.slice(-60).map((c) => +c.close.toFixed(2))
    }
  })
  const indices = INDICES.map((ix) => {
    const history = genCandles(ix.code, ix.base, 120)
    const today = history[history.length - 1]
    const prevClose = history[history.length - 2].close
    return {
      ...ix,
      prevClose,
      open: today.open,
      price: today.close,
      lastPrice: today.close,
      high: today.high,
      low: today.low,
      amount: (1.2e10 + Math.random() * 4e10),
      spark: history.slice(-60).map((c) => +c.close.toFixed(2))
    }
  })
  market = { stocks, indices }
  return market
}

// 推进一个 tick：随机游走更新最新价
export function tickMarket() {
  const m = getMarket()
  m.stocks.forEach((s) => {
    s.lastPrice = s.price
    const pct = (Math.random() - 0.5) * 0.006
    s.price = Math.max(0.01, s.price * (1 + pct))
    s.high = Math.max(s.high, s.price)
    s.low = Math.min(s.low, s.price)
    s.volume += Math.round(Math.random() * 1.2e5)
    s.amount = s.volume * s.price
    s.spark[s.spark.length - 1] = +s.price.toFixed(2)
    const today = s.history[s.history.length - 1]
    today.close = s.price
    today.high = s.high
    today.low = s.low
    today.volume = s.volume
  })
  m.indices.forEach((ix) => {
    ix.lastPrice = ix.price
    const pct = (Math.random() - 0.5) * 0.0022
    ix.price = Math.max(1, ix.price * (1 + pct))
    ix.high = Math.max(ix.high, ix.price)
    ix.low = Math.min(ix.low, ix.price)
    ix.spark[ix.spark.length - 1] = +ix.price.toFixed(2)
  })
  return m
}

// ============ 财经新闻 ============
export const NEWS = [
  {
    id: 1, time: '2026-09-04 14:32', source: '财联社', category: '宏观政策', sentiment: '利好',
    title: '央行宣布降准0.5个百分点 释放长期资金约1万亿元',
    summary: '中国人民银行决定于9月15日下调金融机构存款准备金率0.5个百分点，本次下调后金融机构加权平均存款准备金率约为6.6%，预计释放长期资金约1万亿元，降低银行资金成本每年约150亿元。',
    content: '央行有关负责人表示，此次降准旨在保持流动性合理充裕，支持实体经济恢复发展。市场分析认为，宽松信号明确，利好银行、券商及地产板块，A股有望迎来增量资金入场。'
  },
  {
    id: 2, time: '2026-09-04 13:05', source: '上海证券报', category: '市场动态', sentiment: '利好',
    title: '沪指放量涨1.28%站上3150点 北向资金净买入86亿元',
    summary: '今日A股三大指数集体走强，上证指数收盘涨1.28%报3156.72点，深证成指涨1.74%，创业板指涨2.13%。两市成交额突破1.8万亿元，北向资金全天净买入86.3亿元，为近三个月最大单日净流入。',
    content: '盘面上，券商、半导体、新能源板块领涨。分析人士指出，降准预期升温与外围市场回暖共振，市场风险偏好明显修复，成交量放大显示增量资金正在入场。'
  },
  {
    id: 3, time: '2026-09-04 11:48', source: '证券时报', category: '新能源', sentiment: '利好',
    title: '宁德时代发布新一代麒麟电池 能量密度提升20%',
    summary: '宁德时代在全球新能源大会上发布第三代麒麟电池，系统能量密度达到280Wh/kg，较上一代提升20%，支持10分钟快充，续航里程突破1000公里，已获多家头部车企定点订单。',
    content: '机构研报指出，新电池量产将巩固公司技术壁垒，预计2027年贡献营收超300亿元，维持"买入"评级。'
  },
  {
    id: 4, time: '2026-09-04 10:22', source: '中国证券报', category: '半导体', sentiment: '利好',
    title: '半导体板块异动拉升 中芯国际涨超5%',
    summary: '受国产先进制程突破消息提振，半导体板块早盘集体走强，中芯国际涨5.8%，北方华创、中微公司跟涨。消息面上，国内晶圆厂扩产计划落地，设备招标加速。',
    content: '业内人士表示，半导体国产替代进入深水区，设备与材料环节受益确定性最强，建议关注晶圆代工与封测龙头。'
  },
  {
    id: 5, time: '2026-09-04 09:10', source: '21世纪经济报道', category: '全球市场', sentiment: '中性',
    title: '美联储会议纪要：年内或再降息一次',
    summary: '美联储公布最新会议纪要显示，多数官员认为若通胀继续回落，年内仍有一次25个基点降息空间。美股三大指数收涨，10年期美债收益率回落至3.85%。',
    content: '市场对9月降息概率定价升至72%。分析认为，全球流动性预期改善有利于新兴市场资产表现，但需关注美国非农数据扰动。'
  },
  {
    id: 6, time: '2026-09-03 20:15', source: '证券日报', category: '公司公告', sentiment: '利好',
    title: '贵州茅台半年报：营收同比增长15.8% 拟中期分红',
    summary: '贵州茅台披露2026年半年报，上半年实现营收918亿元，同比增长15.8%；归母净利润456亿元，同比增长16.2%。公司同时公告拟每10股派发现金红利238.8元。',
    content: '券商点评认为，公司直销渠道占比提升与系列酒放量驱动增长超预期，现金流充沛，高股息属性强化配置价值。'
  },
  {
    id: 7, time: '2026-09-03 16:40', source: '财联社', category: '新能源', sentiment: '利空',
    title: '光伏行业产能过剩担忧加剧 隆基绿能跌3.2%',
    summary: '光伏协会发布报告称行业硅料、硅片产能利用率不足55%，价格战持续。受此影响，光伏板块承压，隆基绿能收跌3.2%，通威股份、TCL中环跟跌。',
    content: '机构提示，光伏行业正经历供给侧出清阵痛期，短期盈利承压，但落后产能退出后龙头份额有望进一步集中。'
  },
  {
    id: 8, time: '2026-09-03 15:02', source: '上海证券报', category: '人工智能', sentiment: '利好',
    title: '科大讯飞与华为达成战略合作 共建国产算力大模型',
    summary: '科大讯飞与华为签署全面战略合作协议，双方将基于昇腾算力联合训练新一代星火大模型，并在智慧教育、智能医疗领域推出行业解决方案。',
    content: '双方表示，合作将实现大模型训练全栈国产化，预计带动相关业务收入三年复合增速超40%。'
  },
  {
    id: 9, time: '2026-09-03 11:30', source: '中国证券报', category: '宏观政策', sentiment: '利好',
    title: '金融监管总局：支持中长期资金入市 险资权益比例有望提升',
    summary: '金融监管总局召开座谈会提出，推动保险资金、养老金等中长期资金加大权益市场配置，研究提高险资权益类资产监管比例上限，建立长周期考核机制。',
    content: '据测算，险资权益比例每提升1个百分点，将带来约2500亿元增量资金。市场认为蓝筹红利资产将持续受益。'
  },
  {
    id: 10, time: '2026-09-02 19:48', source: '证券时报', category: '公司公告', sentiment: '利好',
    title: '比亚迪8月新能源汽车销量42.6万辆 同比增长34%',
    summary: '比亚迪公布8月产销快报，新能源汽车销量42.6万辆，同比增长34%；其中海外销售5.8万辆，同比增长112%。1-8月累计销量286万辆，完成全年目标进度超70%。',
    content: '机构认为，公司高端品牌仰望、腾势放量改善盈利结构，出海战略进入收获期，上调全年销量预期至430万辆。'
  },
  {
    id: 11, time: '2026-09-02 14:20', source: '每日经济新闻', category: '有色金属', sentiment: '利好',
    title: '国际金价创历史新高 紫金矿业受益走强',
    summary: '伦敦现货黄金突破2750美元/盎司创历史新高，白银同步走强。A股黄金股集体拉升，紫金矿业涨4.1%，山东黄金、中金黄金涨幅居前。',
    content: '分析认为，降息预期与地缘避险需求共振支撑金价，黄金企业盈利弹性显著，紫金矿业铜金双主业优势突出。'
  },
  {
    id: 12, time: '2026-09-02 10:05', source: '财联社', category: '医药生物', sentiment: '中性',
    title: '新一轮医药集采结果公布 恒瑞医药多款产品中标',
    summary: '第十批国家药品集中采购结果出炉，平均降价58%。恒瑞医药7款产品中标，公司表示以价换量有望巩固市场份额，创新药管线不受集采影响。',
    content: '券商认为集采常态化已被市场充分定价，板块关注点正切换至创新药出海与BD交易进展。'
  },
  {
    id: 13, time: '2026-09-01 16:55', source: '21世纪经济报道', category: '市场动态', sentiment: '中性',
    title: '两市融资余额突破1.6万亿元 杠杆资金活跃度回升',
    summary: '截至8月末，两市融资融券余额达1.62万亿元，其中融资余额1.58万亿元，创年内新高。电子、计算机、非银金融为融资净买入前三行业。',
    content: '历史数据显示，融资余额持续攀升往往伴随市场情绪回暖，但快速攀升后需警惕短期波动加大。'
  },
  {
    id: 14, time: '2026-09-01 09:30', source: '证券日报', category: '消费旅游', sentiment: '利好',
    title: '暑期旅游消费数据超预期 中国中免获机构扎堆调研',
    summary: '文旅部数据显示暑期国内出游人次同比增长18%，离岛免税销售额同比增长22%。近一周32家机构调研中国中免，关注海南封关运作对免税业务的带动。',
    content: '公司表示下半年将加大香化品类促销力度，新开门店稳步推进，目标全年营收恢复双位数增长。'
  }
]

// ============ 量化策略模板 ============
export const STRATEGIES = [
  {
    id: 'ma_cross', name: '双均线交叉策略', type: '趋势跟踪', risk: '中', freq: '中频',
    desc: '快线上穿慢线形成金叉时满仓买入，死叉时清仓离场，捕捉中长期趋势。',
    params: [
      { key: 'fast', label: '快线周期(MA)', value: 5, min: 2, max: 30, step: 1 },
      { key: 'slow', label: '慢线周期(MA)', value: 20, min: 10, max: 120, step: 1 }
    ]
  },
  {
    id: 'macd', name: 'MACD 趋势策略', type: '趋势跟踪', risk: '中', freq: '中频',
    desc: 'DIF 上穿 DEA 金叉买入，下穿死叉卖出，配合零轴过滤假信号。',
    params: [
      { key: 'fast', label: '快线EMA', value: 12, min: 5, max: 20, step: 1 },
      { key: 'slow', label: '慢线EMA', value: 26, min: 15, max: 40, step: 1 },
      { key: 'signal', label: '信号线DEA', value: 9, min: 5, max: 15, step: 1 }
    ]
  },
  {
    id: 'boll', name: '布林带均值回归', type: '震荡反转', risk: '中高', freq: '高频',
    desc: '价格触及布林带下轨超卖买入，触及上轨超买卖出，适合震荡行情。',
    params: [
      { key: 'period', label: '布林带周期', value: 20, min: 10, max: 60, step: 1 },
      { key: 'mult', label: '标准差倍数', value: 2, min: 1, max: 3, step: 0.1 }
    ]
  },
  {
    id: 'rsi', name: 'RSI 超卖反弹策略', type: '震荡反转', risk: '中', freq: '中频',
    desc: 'RSI 低于超卖线买入，高于超买线卖出，捕捉短期超跌反弹机会。',
    params: [
      { key: 'period', label: 'RSI周期', value: 14, min: 6, max: 30, step: 1 },
      { key: 'low', label: '超卖阈值', value: 30, min: 10, max: 40, step: 1 },
      { key: 'high', label: '超买阈值', value: 70, min: 60, max: 90, step: 1 }
    ]
  },
  {
    id: 'momentum', name: '动量突破策略', type: '趋势跟踪', risk: '高', freq: '低频',
    desc: '价格突破 N 日最高价追涨买入，跌破 MA20 或触发止损线离场。',
    params: [
      { key: 'lookback', label: '突破回看周期', value: 20, min: 10, max: 60, step: 1 },
      { key: 'stop', label: '止损比例(%)', value: 8, min: 3, max: 20, step: 1 }
    ]
  }
]

// ============ 回测框架 ============
export const BACKTEST_FRAMEWORKS = [
  { id: 'quant', name: 'QuantEngine 自研框架', desc: '平台内置，支持 Tick 级模拟与 GPU 加速，回测速度最快', tag: '推荐' },
  { id: 'backtrader', name: 'Backtrader', desc: 'Python 社区经典事件驱动框架，指标库丰富' },
  { id: 'vnpy', name: 'vn.py', desc: '国产开源框架，回测与实盘交易接口一体化' },
  { id: 'zipline', name: 'Zipline', desc: 'Quantopian 开源引擎，适合美股日频策略研究' }
]

// ============ 账户 ============
export const ACCOUNTS_INIT = [
  {
    id: 'ACC-001', broker: '模拟账户', type: '模拟盘', accountNo: 'SIM-20260901',
    status: 'active', totalAssets: 1000000, cash: 326500,
    autoTrade: true, strategyId: 'ma_cross', strategyEnabled: true, risk: '稳健型', created: '2026-08-15'
  },
  {
    id: 'ACC-002', broker: '华泰证券', type: '实盘 · A股', accountNo: '6600 **** 2891',
    status: 'connected', totalAssets: 586200, cash: 84200,
    autoTrade: false, strategyId: 'macd', strategyEnabled: true, risk: '平衡型', created: '2026-07-22'
  },
  {
    id: 'ACC-003', broker: '盈透证券 IB', type: '实盘 · 美股', accountNo: 'U **** 7720',
    status: 'connected', totalAssets: 248300, cash: 15600,
    autoTrade: true, strategyId: null, strategyEnabled: false, risk: '进取型', created: '2026-06-08'
  },
  {
    id: 'ACC-004', broker: '东方财富证券', type: '实盘 · A股', accountNo: '8801 **** 6634',
    status: 'disconnected', totalAssets: 120000, cash: 120000,
    autoTrade: false, strategyId: null, strategyEnabled: false, risk: '保守型', created: '2026-09-01'
  }
]

// ============ 持仓（模拟账户 ACC-001） ============
export const POSITIONS_INIT = [
  { code: '600519', qty: 100, cost: 1620.5 },
  { code: '300750', qty: 500, cost: 188.2 },
  { code: '600036', qty: 8000, cost: 33.8 },
  { code: '002594', qty: 300, cost: 232.4 },
  { code: '688981', qty: 1000, cost: 82.6 },
  { code: '601899', qty: 10000, cost: 16.8 },
  { code: '002415', qty: 2000, cost: 30.5 }
]

// 账户历史净值曲线（120个交易日）
export function genEquityCurve(seed, startCapital, days = 120) {
  const rnd = hashSeed('equity-' + seed)
  const dates = tradingDates(days)
  const drift = 0.0006 + rnd() * 0.0008
  const vol = 0.008 + rnd() * 0.008
  let v = startCapital * (0.82 + rnd() * 0.1)
  return dates.map((date) => {
    v = v * (1 + drift + (rnd() - 0.5) * vol * 2)
    return { date, value: Math.round(v) }
  })
}

// ============ 投资偏好默认值 ============
export const DEFAULT_PREFS = {
  risk: '稳健型',
  horizon: '中线（1-6个月）',
  sectors: ['新能源', '人工智能', '医药生物'],
  maxPosition: 25,        // 单票最大仓位 %
  stopLoss: 8,            // 止损线 %
  takeProfit: 30,         // 止盈线 %
  autoRebalance: true,    // 自动调仓
  tradeNotify: true,      // 交易提醒
  dailyReport: true,      // 每日复盘报告
  benchmark: '沪深300'
}

export const SECTORS = ['白酒消费', '食品消费', '家电消费', '消费旅游', '银行金融', '券商金融', '保险金融', '新能源', '新能源车', '光伏新能源', '有色金属', '半导体', '人工智能', '电子科技', '通信运营', '医药生物', '公用事业']
export const RISK_LEVELS = ['保守型', '稳健型', '平衡型', '进取型', '激进型']
export const HORIZONS = ['短线（1个月内）', '中线（1-6个月）', '长线（1年以上）']
export const BENCHMARKS = ['沪深300', '上证指数', '中证500', '创业板指']
