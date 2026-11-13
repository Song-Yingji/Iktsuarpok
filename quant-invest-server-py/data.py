# -*- coding: utf-8 -*-
"""数据引擎：真实历史行情（Baostock）、实时快照（easyquotation）、财经新闻（财联社）与静态配置。"""
import datetime
import json
import os
import threading

from utils import hash_seed

# ============ 大盘指数 ============
INDICES = [
    {'code': 'SH000001', 'name': '上证指数', 'base': 3128.45},
    {'code': 'SZ399001', 'name': '深证成指', 'base': 9862.13},
    {'code': 'SZ399006', 'name': '创业板指', 'base': 1932.76},
    {'code': 'SH000300', 'name': '沪深300', 'base': 3685.22},
]

# ============ 个股 ============
# code, name, sector 行业板块, base 基准价(今开附近), pe 市盈率
STOCKS = [
    {'code': '600519', 'name': '贵州茅台', 'sector': '白酒消费', 'base': 1685.0, 'pe': 24.5},
    {'code': '000858', 'name': '五粮液', 'sector': '白酒消费', 'base': 142.3, 'pe': 18.2},
    {'code': '603288', 'name': '海天味业', 'sector': '食品消费', 'base': 38.64, 'pe': 35.2},
    {'code': '600887', 'name': '伊利股份', 'sector': '食品消费', 'base': 26.35, 'pe': 16.8},
    {'code': '000333', 'name': '美的集团', 'sector': '家电消费', 'base': 68.92, 'pe': 13.4},
    {'code': '601888', 'name': '中国中免', 'sector': '消费旅游', 'base': 68.15, 'pe': 24.6},
    {'code': '601318', 'name': '中国平安', 'sector': '保险金融', 'base': 48.65, 'pe': 8.6},
    {'code': '600036', 'name': '招商银行', 'sector': '银行金融', 'base': 35.42, 'pe': 6.2},
    {'code': '000001', 'name': '平安银行', 'sector': '银行金融', 'base': 11.28, 'pe': 4.8},
    {'code': '601988', 'name': '中国银行', 'sector': '银行金融', 'base': 4.62, 'pe': 6.0},
    {'code': '600030', 'name': '中信证券', 'sector': '券商金融', 'base': 22.86, 'pe': 14.3},
    {'code': '300059', 'name': '东方财富', 'sector': '券商金融', 'base': 15.63, 'pe': 28.4},
    {'code': '300750', 'name': '宁德时代', 'sector': '新能源', 'base': 198.75, 'pe': 22.1},
    {'code': '002594', 'name': '比亚迪', 'sector': '新能源车', 'base': 245.6, 'pe': 20.8},
    {'code': '601012', 'name': '隆基绿能', 'sector': '光伏新能源', 'base': 18.42, 'pe': 12.5},
    {'code': '601899', 'name': '紫金矿业', 'sector': '有色金属', 'base': 17.56, 'pe': 12.1},
    {'code': '688981', 'name': '中芯国际', 'sector': '半导体', 'base': 88.34, 'pe': 45.6},
    {'code': '000725', 'name': '京东方A', 'sector': '电子科技', 'base': 4.18, 'pe': 22.7},
    {'code': '002415', 'name': '海康威视', 'sector': '人工智能', 'base': 32.18, 'pe': 19.7},
    {'code': '002230', 'name': '科大讯飞', 'sector': '人工智能', 'base': 45.26, 'pe': 72.3},
    {'code': '600050', 'name': '中国联通', 'sector': '通信运营', 'base': 5.46, 'pe': 16.2},
    {'code': '600276', 'name': '恒瑞医药', 'sector': '医药生物', 'base': 46.85, 'pe': 38.9},
    {'code': '300760', 'name': '迈瑞医疗', 'sector': '医药生物', 'base': 268.4, 'pe': 26.3},
    {'code': '600900', 'name': '长江电力', 'sector': '公用事业', 'base': 27.83, 'pe': 19.5},
    {'code': '000568', 'name': '泸州老窖', 'sector': '白酒消费', 'base': 76.74, 'pe': 19.7},
    {'code': '002304', 'name': '洋河股份', 'sector': '白酒消费', 'base': 35.89, 'pe': 874.0},
    {'code': '600809', 'name': '山西汾酒', 'sector': '白酒消费', 'base': 125.0, 'pe': 16.6},
    {'code': '000596', 'name': '古井贡酒', 'sector': '白酒消费', 'base': 105.8, 'pe': 30.3},
    {'code': '603369', 'name': '今世缘', 'sector': '白酒消费', 'base': 32.47, 'pe': 15.8},
    {'code': '000799', 'name': '酒鬼酒', 'sector': '白酒消费', 'base': 34.36, 'pe': -592.4},
    {'code': '603589', 'name': '口子窖', 'sector': '白酒消费', 'base': 17.7, 'pe': 33.6},
    {'code': '603198', 'name': '迎驾贡酒', 'sector': '白酒消费', 'base': 44.1, 'pe': 17.2},
    {'code': '000895', 'name': '双汇发展', 'sector': '食品消费', 'base': 24.32, 'pe': 17.6},
    {'code': '603345', 'name': '安井食品', 'sector': '食品消费', 'base': 85.49, 'pe': 18.4},
    {'code': '002216', 'name': '三全食品', 'sector': '食品消费', 'base': 11.45, 'pe': 17.9},
    {'code': '603866', 'name': '桃李面包', 'sector': '食品消费', 'base': 4.05, 'pe': 34.1},
    {'code': '603517', 'name': '绝味食品', 'sector': '食品消费', 'base': 10.86, 'pe': -21.7},
    {'code': '002695', 'name': '煌上煌', 'sector': '食品消费', 'base': 9.85, 'pe': 65.8},
    {'code': '600872', 'name': '中炬高新', 'sector': '食品消费', 'base': 18.99, 'pe': 19.1},
    {'code': '603027', 'name': '千禾味业', 'sector': '食品消费', 'base': 6.91, 'pe': 27.5},
    {'code': '600305', 'name': '恒顺醋业', 'sector': '食品消费', 'base': 6.73, 'pe': 49.0},
    {'code': '002507', 'name': '涪陵榨菜', 'sector': '食品消费', 'base': 11.42, 'pe': 18.6},
    {'code': '000651', 'name': '格力电器', 'sector': '家电消费', 'base': 38.89, 'pe': 8.8},
    {'code': '600690', 'name': '海尔智家', 'sector': '家电消费', 'base': 20.78, 'pe': 11.2},
    {'code': '000921', 'name': '海信家电', 'sector': '家电消费', 'base': 21.85, 'pe': 13.6},
    {'code': '600060', 'name': '海信视像', 'sector': '家电消费', 'base': 25.28, 'pe': 12.4},
    {'code': '002508', 'name': '老板电器', 'sector': '家电消费', 'base': 15.65, 'pe': 15.8},
    {'code': '002032', 'name': '苏泊尔', 'sector': '家电消费', 'base': 44.36, 'pe': 17.6},
    {'code': '002242', 'name': '九阳股份', 'sector': '家电消费', 'base': 26.65, 'pe': 307.9},
    {'code': '002959', 'name': '小熊电器', 'sector': '家电消费', 'base': 32.54, 'pe': 17.0},
    {'code': '600054', 'name': '黄山旅游', 'sector': '消费旅游', 'base': 10.26, 'pe': 29.6},
    {'code': '000888', 'name': '峨眉山A', 'sector': '消费旅游', 'base': 10.26, 'pe': 27.2},
    {'code': '002033', 'name': '丽江股份', 'sector': '消费旅游', 'base': 8.24, 'pe': 18.2},
    {'code': '600749', 'name': '西藏旅游', 'sector': '消费旅游', 'base': 11.53, 'pe': 109.3},
    {'code': '000430', 'name': '张家界', 'sector': '消费旅游', 'base': 6.06, 'pe': -24.6},
    {'code': '600593', 'name': '大连圣亚', 'sector': '消费旅游', 'base': 41.2, 'pe': 102.3},
    {'code': '002159', 'name': '三特索道', 'sector': '消费旅游', 'base': 13.19, 'pe': 18.1},
    {'code': '603199', 'name': '九华旅游', 'sector': '消费旅游', 'base': 33.5, 'pe': 16.6},
    {'code': '601398', 'name': '工商银行', 'sector': '银行金融', 'base': 8.69, 'pe': 8.1},
    {'code': '601939', 'name': '建设银行', 'sector': '银行金融', 'base': 12.01, 'pe': 8.8},
    {'code': '601288', 'name': '农业银行', 'sector': '银行金融', 'base': 7.26, 'pe': 8.3},
    {'code': '601328', 'name': '交通银行', 'sector': '银行金融', 'base': 8.45, 'pe': 7.5},
    {'code': '601658', 'name': '邮储银行', 'sector': '银行金融', 'base': 5.62, 'pe': 7.4},
    {'code': '601998', 'name': '中信银行', 'sector': '银行金融', 'base': 9.16, 'pe': 7.0},
    {'code': '601818', 'name': '光大银行', 'sector': '银行金融', 'base': 3.16, 'pe': 6.2},
    {'code': '600016', 'name': '民生银行', 'sector': '银行金融', 'base': 3.39, 'pe': 5.6},
    {'code': '600000', 'name': '浦发银行', 'sector': '银行金融', 'base': 10.21, 'pe': 6.6},
    {'code': '601166', 'name': '兴业银行', 'sector': '银行金融', 'base': 19.58, 'pe': 5.5},
    {'code': '600015', 'name': '华夏银行', 'sector': '银行金融', 'base': 6.6, 'pe': 4.4},
    {'code': '601169', 'name': '北京银行', 'sector': '银行金融', 'base': 6.01, 'pe': 5.9},
    {'code': '601229', 'name': '上海银行', 'sector': '银行金融', 'base': 8.33, 'pe': 6.0},
    {'code': '601688', 'name': '华泰证券', 'sector': '券商金融', 'base': 17.11, 'pe': 8.3},
    {'code': '601211', 'name': '国泰海通', 'sector': '券商金融', 'base': 16.0, 'pe': 9.2},
    {'code': '000776', 'name': '广发证券', 'sector': '券商金融', 'base': 18.56, 'pe': 7.7},
    {'code': '000166', 'name': '申万宏源', 'sector': '券商金融', 'base': 4.25, 'pe': 12.3},
    {'code': '601881', 'name': '中国银河', 'sector': '券商金融', 'base': 11.57, 'pe': 10.1},
    {'code': '002736', 'name': '国信证券', 'sector': '券商金融', 'base': 8.81, 'pe': 10.7},
    {'code': '601995', 'name': '中金公司', 'sector': '券商金融', 'base': 27.44, 'pe': 13.2},
    {'code': '601066', 'name': '中信建投', 'sector': '券商金融', 'base': 21.72, 'pe': 13.4},
    {'code': '601788', 'name': '光大证券', 'sector': '券商金融', 'base': 13.52, 'pe': 14.3},
    {'code': '601628', 'name': '中国人寿', 'sector': '保险金融', 'base': 34.3, 'pe': 12.8},
    {'code': '601601', 'name': '中国太保', 'sector': '保险金融', 'base': 30.96, 'pe': 6.7},
    {'code': '601336', 'name': '新华保险', 'sector': '保险金融', 'base': 51.11, 'pe': 6.2},
    {'code': '601319', 'name': '中国人保', 'sector': '保险金融', 'base': 7.1, 'pe': 9.9},
    {'code': '300014', 'name': '亿纬锂能', 'sector': '新能源', 'base': 47.0, 'pe': 15.8},
    {'code': '002074', 'name': '国轩高科', 'sector': '新能源', 'base': 23.92, 'pe': 62.1},
    {'code': '300207', 'name': '欣旺达', 'sector': '新能源', 'base': 17.48, 'pe': 121.9},
    {'code': '688567', 'name': '孚能科技', 'sector': '新能源', 'base': 9.48, 'pe': -12.1},
    {'code': '300438', 'name': '鹏辉能源', 'sector': '新能源', 'base': 41.02, 'pe': 16.3},
    {'code': '688063', 'name': '派能科技', 'sector': '新能源', 'base': 36.46, 'pe': 89.5},
    {'code': '002202', 'name': '金风科技', 'sector': '新能源', 'base': 14.66, 'pe': 20.2},
    {'code': '601615', 'name': '明阳智能', 'sector': '新能源', 'base': 7.88, 'pe': -16.4},
    {'code': '300772', 'name': '运达股份', 'sector': '新能源', 'base': 8.85, 'pe': -44.1},
    {'code': '600406', 'name': '国电南瑞', 'sector': '新能源', 'base': 23.18, 'pe': 22.3},
    {'code': '002028', 'name': '思源电气', 'sector': '新能源', 'base': 113.19, 'pe': 26.5},
    {'code': '600089', 'name': '特变电工', 'sector': '新能源', 'base': 18.12, 'pe': 22.7},
    {'code': '002518', 'name': '科士达', 'sector': '新能源', 'base': 27.28, 'pe': 23.8},
    {'code': '000625', 'name': '长安汽车', 'sector': '新能源车', 'base': 6.9, 'pe': 63.4},
    {'code': '600104', 'name': '上汽集团', 'sector': '新能源车', 'base': 10.0, 'pe': 15.0},
    {'code': '601238', 'name': '广汽集团', 'sector': '新能源车', 'base': 4.79, 'pe': -4.3},
    {'code': '601633', 'name': '长城汽车', 'sector': '新能源车', 'base': 13.1, 'pe': 22.2},
    {'code': '601127', 'name': '赛力斯', 'sector': '新能源车', 'base': 42.3, 'pe': 212.0},
    {'code': '600418', 'name': '江淮汽车', 'sector': '新能源车', 'base': 19.04, 'pe': -30.5},
    {'code': '000800', 'name': '一汽解放', 'sector': '新能源车', 'base': 5.36, 'pe': 30.8},
    {'code': '600166', 'name': '福田汽车', 'sector': '新能源车', 'base': 2.36, 'pe': 13.4},
    {'code': '000550', 'name': '江铃汽车', 'sector': '新能源车', 'base': 15.9, 'pe': 10.2},
    {'code': '600066', 'name': '宇通客车', 'sector': '新能源车', 'base': 30.12, 'pe': 12.2},
    {'code': '600660', 'name': '福耀玻璃', 'sector': '新能源车', 'base': 55.85, 'pe': 17.7},
    {'code': '600438', 'name': '通威股份', 'sector': '光伏新能源', 'base': 11.71, 'pe': -4.8},
    {'code': '002459', 'name': '晶澳科技', 'sector': '光伏新能源', 'base': 6.5, 'pe': -4.6},
    {'code': '688599', 'name': '天合光能', 'sector': '光伏新能源', 'base': 10.44, 'pe': -5.1},
    {'code': '688223', 'name': '晶科能源', 'sector': '光伏新能源', 'base': 4.03, 'pe': -6.5},
    {'code': '688472', 'name': '阿特斯', 'sector': '光伏新能源', 'base': 8.42, 'pe': -448.3},
    {'code': '300118', 'name': '东方日升', 'sector': '光伏新能源', 'base': 9.74, 'pe': -3.4},
    {'code': '002129', 'name': 'TCL中环', 'sector': '光伏新能源', 'base': 9.38, 'pe': -4.7},
    {'code': '300274', 'name': '阳光电源', 'sector': '光伏新能源', 'base': 78.26, 'pe': 19.8},
    {'code': '300763', 'name': '锦浪科技', 'sector': '光伏新能源', 'base': 47.2, 'pe': 42.9},
    {'code': '688390', 'name': '固德威', 'sector': '光伏新能源', 'base': 48.96, 'pe': 24.5},
    {'code': '603993', 'name': '洛阳钼业', 'sector': '有色金属', 'base': 13.34, 'pe': 9.5},
    {'code': '600547', 'name': '山东黄金', 'sector': '有色金属', 'base': 24.91, 'pe': 29.0},
    {'code': '600489', 'name': '中金黄金', 'sector': '有色金属', 'base': 19.69, 'pe': 13.7},
    {'code': '002155', 'name': '湖南黄金', 'sector': '有色金属', 'base': 19.02, 'pe': 18.3},
    {'code': '600988', 'name': '赤峰黄金', 'sector': '有色金属', 'base': 36.03, 'pe': 24.1},
    {'code': '000975', 'name': '山金国际', 'sector': '有色金属', 'base': 22.49, 'pe': 16.8},
    {'code': '600362', 'name': '江西铜业', 'sector': '有色金属', 'base': 32.29, 'pe': 8.7},
    {'code': '000630', 'name': '铜陵有色', 'sector': '有色金属', 'base': 4.83, 'pe': 11.4},
    {'code': '000878', 'name': '云南铜业', 'sector': '有色金属', 'base': 13.38, 'pe': 15.1},
    {'code': '601600', 'name': '中国铝业', 'sector': '有色金属', 'base': 8.06, 'pe': 7.0},
    {'code': '000807', 'name': '云铝股份', 'sector': '有色金属', 'base': 23.31, 'pe': 6.1},
    {'code': '000933', 'name': '神火股份', 'sector': '有色金属', 'base': 24.31, 'pe': 6.8},
    {'code': '002460', 'name': '赣锋锂业', 'sector': '有色金属', 'base': 36.59, 'pe': 11.6},
    {'code': '002466', 'name': '天齐锂业', 'sector': '有色金属', 'base': 35.16, 'pe': 10.2},
    {'code': '603501', 'name': '豪威集团', 'sector': '半导体', 'base': 85.74, 'pe': 34.4},
    {'code': '002371', 'name': '北方华创', 'sector': '半导体', 'base': 558.8, 'pe': 70.3},
    {'code': '688012', 'name': '中微公司', 'sector': '半导体', 'base': 252.55, 'pe': 48.1},
    {'code': '603986', 'name': '兆易创新', 'sector': '半导体', 'base': 258.85, 'pe': 15.7},
    {'code': '300782', 'name': '卓胜微', 'sector': '半导体', 'base': 54.39, 'pe': -35.1},
    {'code': '300661', 'name': '圣邦股份', 'sector': '半导体', 'base': 84.19, 'pe': 61.4},
    {'code': '688008', 'name': '澜起科技', 'sector': '半导体', 'base': 162.89, 'pe': 51.8},
    {'code': '002049', 'name': '紫光国微', 'sector': '半导体', 'base': 51.62, 'pe': 35.7},
    {'code': '600584', 'name': '长电科技', 'sector': '半导体', 'base': 54.45, 'pe': 43.7},
    {'code': '002156', 'name': '通富微电', 'sector': '半导体', 'base': 48.36, 'pe': 22.5},
    {'code': '002185', 'name': '华天科技', 'sector': '半导体', 'base': 14.79, 'pe': 41.8},
    {'code': '600460', 'name': '士兰微', 'sector': '半导体', 'base': 23.93, 'pe': 68.3},
    {'code': '688396', 'name': '华润微', 'sector': '半导体', 'base': 48.25, 'pe': 57.6},
    {'code': '300373', 'name': '扬杰科技', 'sector': '半导体', 'base': 75.4, 'pe': 27.0},
    {'code': '000100', 'name': 'TCL科技', 'sector': '电子科技', 'base': 4.46, 'pe': 14.9},
    {'code': '000050', 'name': '深天马A', 'sector': '电子科技', 'base': 5.47, 'pe': -9.4},
    {'code': '002387', 'name': '维信诺', 'sector': '电子科技', 'base': 6.29, 'pe': -2.7},
    {'code': '002475', 'name': '立讯精密', 'sector': '电子科技', 'base': 50.82, 'pe': 21.7},
    {'code': '002241', 'name': '歌尔股份', 'sector': '电子科技', 'base': 24.66, 'pe': 22.2},
    {'code': '300433', 'name': '蓝思科技', 'sector': '电子科技', 'base': 28.05, 'pe': 57.1},
    {'code': '002600', 'name': '领益智造', 'sector': '电子科技', 'base': 11.47, 'pe': 41.4},
    {'code': '300115', 'name': '长盈精密', 'sector': '电子科技', 'base': 28.57, 'pe': 613.1},
    {'code': '002938', 'name': '鹏鼎控股', 'sector': '电子科技', 'base': 52.47, 'pe': 32.2},
    {'code': '002463', 'name': '沪电股份', 'sector': '电子科技', 'base': 91.33, 'pe': 26.3},
    {'code': '002916', 'name': '深南电路', 'sector': '电子科技', 'base': 231.34, 'pe': 31.0},
    {'code': '600183', 'name': '生益科技', 'sector': '电子科技', 'base': 75.71, 'pe': 24.1},
    {'code': '300476', 'name': '胜宏科技', 'sector': '电子科技', 'base': 137.8, 'pe': 30.4},
    {'code': '688256', 'name': '寒武纪', 'sector': '人工智能', 'base': 973.0, 'pe': 146.8},
    {'code': '688041', 'name': '海光信息', 'sector': '人工智能', 'base': 202.37, 'pe': 137.1},
    {'code': '603019', 'name': '中科曙光', 'sector': '人工智能', 'base': 80.02, 'pe': 39.9},
    {'code': '000977', 'name': '浪潮信息', 'sector': '人工智能', 'base': 55.98, 'pe': 16.9},
    {'code': '601138', 'name': '工业富联', 'sector': '人工智能', 'base': 43.35, 'pe': 16.2},
    {'code': '000938', 'name': '紫光股份', 'sector': '人工智能', 'base': 25.23, 'pe': 23.6},
    {'code': '002396', 'name': '星网锐捷', 'sector': '人工智能', 'base': 25.47, 'pe': 27.5},
    {'code': '300454', 'name': '深信服', 'sector': '人工智能', 'base': 119.06, 'pe': 49.0},
    {'code': '300024', 'name': '机器人', 'sector': '人工智能', 'base': 13.27, 'pe': -37.3},
    {'code': '600941', 'name': '中国移动', 'sector': '通信运营', 'base': 98.7, 'pe': 16.7},
    {'code': '601728', 'name': '中国电信', 'sector': '通信运营', 'base': 6.61, 'pe': 21.1},
    {'code': '000063', 'name': '中兴通讯', 'sector': '通信运营', 'base': 28.03, 'pe': 30.8},
    {'code': '600498', 'name': '烽火通信', 'sector': '通信运营', 'base': 29.17, 'pe': 166.5},
    {'code': '300308', 'name': '中际旭创', 'sector': '通信运营', 'base': 508.9, 'pe': 23.1},
    {'code': '300502', 'name': '新易盛', 'sector': '通信运营', 'base': 205.58, 'pe': 19.7},
    {'code': '603259', 'name': '药明康德', 'sector': '医药生物', 'base': 150.34, 'pe': 17.2},
    {'code': '300015', 'name': '爱尔眼科', 'sector': '医药生物', 'base': 8.65, 'pe': 33.1},
    {'code': '300122', 'name': '智飞生物', 'sector': '医药生物', 'base': 13.85, 'pe': -2.4},
    {'code': '000661', 'name': '长春高新', 'sector': '医药生物', 'base': 71.03, 'pe': -68.4},
    {'code': '600436', 'name': '片仔癀', 'sector': '医药生物', 'base': 129.9, 'pe': 59.5},
    {'code': '000538', 'name': '云南白药', 'sector': '医药生物', 'base': 54.66, 'pe': 18.8},
    {'code': '600085', 'name': '同仁堂', 'sector': '医药生物', 'base': 23.96, 'pe': 37.4},
    {'code': '600332', 'name': '白云山', 'sector': '医药生物', 'base': 19.47, 'pe': 14.6},
    {'code': '000963', 'name': '华东医药', 'sector': '医药生物', 'base': 26.22, 'pe': 13.4},
    {'code': '600196', 'name': '复星医药', 'sector': '医药生物', 'base': 22.81, 'pe': 17.3},
    {'code': '002422', 'name': '科伦药业', 'sector': '医药生物', 'base': 43.44, 'pe': 35.1},
    {'code': '002294', 'name': '信立泰', 'sector': '医药生物', 'base': 29.78, 'pe': 46.4},
    {'code': '300003', 'name': '乐普医疗', 'sector': '医药生物', 'base': 12.17, 'pe': 34.1},
    {'code': '688271', 'name': '联影医疗', 'sector': '医药生物', 'base': 115.39, 'pe': 53.3},
    {'code': '300529', 'name': '健帆生物', 'sector': '医药生物', 'base': 19.26, 'pe': 23.5},
    {'code': '002007', 'name': '华兰生物', 'sector': '医药生物', 'base': 12.0, 'pe': 37.3},
    {'code': '600161', 'name': '天坛生物', 'sector': '医药生物', 'base': 12.22, 'pe': 34.5},
    {'code': '000513', 'name': '丽珠集团', 'sector': '医药生物', 'base': 31.53, 'pe': 18.0},
    {'code': '600025', 'name': '华能水电', 'sector': '公用事业', 'base': 10.83, 'pe': 23.7},
    {'code': '600886', 'name': '国投电力', 'sector': '公用事业', 'base': 15.6, 'pe': 18.0},
    {'code': '600011', 'name': '华能国际', 'sector': '公用事业', 'base': 7.63, 'pe': 16.2},
    {'code': '600027', 'name': '华电国际', 'sector': '公用事业', 'base': 5.1, 'pe': 16.7},
    {'code': '601985', 'name': '中国核电', 'sector': '公用事业', 'base': 9.66, 'pe': 27.0},
    {'code': '003816', 'name': '中国广核', 'sector': '公用事业', 'base': 4.64, 'pe': 21.6},
    {'code': '600905', 'name': '三峡能源', 'sector': '公用事业', 'base': 3.26, 'pe': 112.2},
    {'code': '300142', 'name': '沃森生物', 'sector': '医药生物', 'base': 11.01, 'pe': 806.4},
]


# ============ 真实历史行情（Baostock，前复权，截至最近已收盘交易日） ============
_HISTORY_CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '_history_cache.json')

# 迷你走势（spark）时间窗口：取最近多少个交易日收盘价。
# 前端对 spark 做归一化（以窗口首日为基准的累计涨跌幅），窗口取 120 天（约半年，指数历史缓存上限）。
SPARK_DAYS = 120


def _bs_symbol(code):
    """转为 Baostock 证券代码：600519 -> sh.600519，SH000001 -> sh.000001。"""
    c = code.upper()
    if c.startswith('SH'):
        return 'sh.' + c[2:]
    if c.startswith('SZ'):
        return 'sz.' + c[2:]
    if c.startswith('6'):
        return 'sh.' + c
    if c.startswith(('0', '3')):
        return 'sz.' + c
    return c


def _fetch_real_histories():
    """一次性拉取全部标的真实历史日K，返回 {code: [candle]}；失败返回 None。

    个股用前复权(adjustflag=2)、指数用不复权(3)。历史只保留到最近一个已收盘
    交易日（剔除今天这根），今日行情交给实时源 easyquotation，实现「历史K线与
    今日实时分离」，从而历史回测口径一致、不被盘中实时价污染。
    """
    try:
        import baostock as bs
    except Exception:
        return None

    try:
        lg = bs.login()
    except Exception:
        return None
    if getattr(lg, 'error_code', '1') != '0':
        return None
    try:
        today = datetime.date.today()
        today_s = today.strftime('%Y-%m-%d')
        specs = [('2', s) for s in STOCKS] + [('3', i) for i in INDICES]
        result = {}
        for adjust, s in specs:
            code = s['code']
            days = 240 if adjust == '2' else 120
            start = (today - datetime.timedelta(days=int(days * 1.6))).strftime('%Y-%m-%d')
            try:
                rs = bs.query_history_k_data_plus(
                    _bs_symbol(code), 'date,open,high,low,close,volume',
                    start_date=start, end_date=today_s,
                    frequency='d', adjustflag=adjust)
            except Exception:
                continue
            rows = []
            while getattr(rs, 'error_code', '1') == '0' and rs.next():
                rows.append(rs.get_row_data())
            if not rows:
                continue
            candles = []
            for r in rows:
                try:
                    d, o, h, l, c, v = r[0], float(r[1]), float(r[2]), float(r[3]), float(r[4]), float(r[5])
                except (TypeError, ValueError, IndexError):
                    continue
                if d >= today_s:
                    continue
                candles.append({'date': d, 'open': o, 'high': h, 'low': l, 'close': c, 'volume': v})
            if candles:
                result[code] = candles[-days:]
        return result or None
    finally:
        try:
            bs.logout()
        except Exception:
            pass


def _load_history_cache():
    try:
        with open(_HISTORY_CACHE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _save_history_cache(data):
    try:
        with open(_HISTORY_CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f)
    except OSError:
        pass


def _apply_histories(data):
    """把真实历史写入内存行情项（实时 tick 会继续覆盖 spark 末点，不冲突）。"""
    m = _market
    if not m or not data:
        return
    for s in m['stocks']:
        if s['code'] in data:
            s['history'] = data[s['code']]
            s['spark'] = [round(c['close'], 2) for c in s['history'][-SPARK_DAYS:]]
    for ix in m['indices']:
        if ix['code'] in data:
            ix['spark'] = [round(c['close'], 2) for c in data[ix['code']][-SPARK_DAYS:]]


def _refresh_real_histories():
    """后台任务：拉真实历史，成功后更新内存并写本地缓存；失败标记历史不可用。"""
    m = _market
    data = _fetch_real_histories()
    if data:
        _apply_histories(data)
        _save_history_cache(data)
        if m is not None:
            m['historyError'] = False
    elif m is not None:
        # 拉取失败且内存中仍无任何真实历史 → 标记不可用（前端提示，不回退模拟）
        m['historyError'] = not any(s['history'] for s in m['stocks'])


# ============ 行情引擎（单例，模拟实时推送） ============
_market = None


def get_market():
    global _market
    if _market:
        return _market

    cached = _load_history_cache() or {}

    stocks = []
    for s in STOCKS:
        history = cached.get(s['code']) or []
        if history:
            last = history[-1]  # 最近一个已收盘交易日（昨收）
            prev_close = last['close']
            volume = last['volume']
            amount = last['volume'] * last['close']
            spark = [round(c['close'], 2) for c in history[-SPARK_DAYS:]]
        else:
            prev_close = s['base']
            volume = 0
            amount = 0
            spark = []
        rnd = hash_seed('meta-' + s['code'])
        item = dict(s)
        item.update({
            'history': history,
            'prevClose': prev_close,
            'open': prev_close,
            'price': prev_close,
            'lastPrice': prev_close,
            'high': prev_close,
            'low': prev_close,
            'volume': volume,
            'amount': amount,
            'turnover': 0.4 + rnd() * 3.2,
            'spark': spark,
        })
        stocks.append(item)

    indices = []
    for ix in INDICES:
        history = cached.get(ix['code']) or []
        if history:
            last = history[-1]
            prev_close = last['close']
            spark = [round(c['close'], 2) for c in history[-SPARK_DAYS:]]
        else:
            prev_close = ix['base']
            spark = []
        item = dict(ix)
        item.update({
            'prevClose': prev_close,
            'open': prev_close,
            'price': prev_close,
            'lastPrice': prev_close,
            'high': prev_close,
            'low': prev_close,
            'amount': 0,
            'spark': spark,
        })
        indices.append(item)

    _market = {
        'stocks': stocks,
        'indices': indices,
        'realtimeError': False,
        'historyError': not any(s['history'] for s in stocks),
    }

    # 后台拉真实历史：有缓存会刷新最新，无缓存则首次补全（失败标记 historyError）
    try:
        threading.Thread(target=_refresh_real_histories, daemon=True).start()
    except Exception:
        pass
    return _market


def _to_prefixed(code):
    """把内部代码（如 600519 / SH000001）转换为 easyquotation 带市场前缀的代码。"""
    c = code.upper()
    if c.startswith('SH'):
        return 'sh' + c[2:]
    if c.startswith('SZ'):
        return 'sz' + c[2:]
    if c.startswith('6'):
        return 'sh' + c
    if c.startswith(('0', '3')):
        return 'sz' + c
    if c.startswith(('4', '8')):
        return 'bj' + c
    return c


_quotation = None


def _get_quotation():
    """惰性初始化 easyquotation 新浪行情源，失败返回 None。"""
    global _quotation
    if _quotation is False:
        return None
    if _quotation is None:
        try:
            import easyquotation
            _quotation = easyquotation.use('sina')
        except Exception:
            _quotation = False
            return None
    return _quotation


def _fetch_realtime(codes):
    """拉取一组代码的实时行情，返回 {原始code: quote}；失败返回 None。"""
    q = _get_quotation()
    if q is None:
        return None
    prefixed_codes = [_to_prefixed(c) for c in codes]
    try:
        data = q.stocks(prefixed_codes, prefix=True)
    except Exception:
        return None
    prefix_map = {_to_prefixed(c): c for c in codes}
    result = {}
    for k, v in (data or {}).items():
        orig = prefix_map.get(k)
        if orig:
            result[orig] = v
    return result


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _apply_stock_quote(s, q):
    """把 easyquotation 行情写入个股字典。"""
    now = _num(q.get('now')) if isinstance(q, dict) else None
    if now is None:
        return
    s['lastPrice'] = s['price']
    s['price'] = now
    if _num(q.get('open')) is not None:
        s['open'] = _num(q.get('open'))
    if _num(q.get('high')) is not None:
        s['high'] = _num(q.get('high'))
    if _num(q.get('low')) is not None:
        s['low'] = _num(q.get('low'))
    if _num(q.get('close')) is not None:
        s['prevClose'] = _num(q.get('close'))
    # 新浪语义：turnover=成交量(股)，volume=成交额(元)
    if _num(q.get('turnover')) is not None:
        s['volume'] = int(_num(q.get('turnover')))
    if _num(q.get('volume')) is not None:
        s['amount'] = _num(q.get('volume'))
    if s['spark']:
        s['spark'][-1] = round(now, 2)
    else:
        s['spark'].append(round(now, 2))


def _apply_index_quote(ix, q):
    """把 easyquotation 行情写入指数字典。"""
    now = _num(q.get('now')) if isinstance(q, dict) else None
    if now is None:
        return
    ix['lastPrice'] = ix['price']
    ix['price'] = now
    if _num(q.get('open')) is not None:
        ix['open'] = _num(q.get('open'))
    if _num(q.get('high')) is not None:
        ix['high'] = _num(q.get('high'))
    if _num(q.get('low')) is not None:
        ix['low'] = _num(q.get('low'))
    if _num(q.get('close')) is not None:
        ix['prevClose'] = _num(q.get('close'))
    if ix['spark']:
        ix['spark'][-1] = round(now, 2)
    else:
        ix['spark'].append(round(now, 2))


def tick_market():
    """推进一个 tick：只用真实行情，失败标记异常（不回退模拟）。"""
    m = get_market()
    codes = [s['code'] for s in m['stocks']] + [i['code'] for i in m['indices']]
    quotes = _fetch_realtime(codes)
    if quotes:
        for s in m['stocks']:
            q = quotes.get(s['code'])
            if q:
                _apply_stock_quote(s, q)
        for ix in m['indices']:
            q = quotes.get(ix['code'])
            if q:
                _apply_index_quote(ix, q)
        m['realtimeError'] = False
    else:
        # 实时行情源失效：保持价格不动，标记异常，交给前端提示
        m['realtimeError'] = True
    return m


# ============ 财经新闻（财联社电报，实时） ============
_news = []
_news_error = True
_news_lock = threading.Lock()

# 板块分类关键词（按顺序命中即归入对应分类）
_NEWS_CATEGORY_RULES = [
    ('宏观政策', ['央行', '降准', '降息', '财政', '发改委', '国常会', '监管', '政策', '利率', '存款准备金', 'LPR', '证监会']),
    ('公司公告', ['公告', '披露', '中标', '定增', '回购', '增持', '减持', '分红', '重组', '并购', '业绩', '半年报', '年报', '季报', '异动']),
    ('新能源', ['新能源', '光伏', '锂电', '锂电池', '储能', '风电', '充电桩', '氢能', '宁德时代', '比亚迪']),
    ('半导体', ['半导体', '芯片', '晶圆', '光刻', '集成电路', '中芯', '存储', '封装']),
    ('人工智能', ['人工智能', 'AI', '大模型', '算力', '机器人', '智能驾驶']),
    ('医药生物', ['医药', '医疗', '疫苗', '创新药', '集采', '医保', '药']),
    ('银行金融', ['银行', '存款', '贷款', '房贷', '信贷', '保险']),
    ('券商金融', ['券商', '证券', 'IPO', '融资融券', '两融', '北向']),
    ('有色金属', ['黄金', '白银', '铜', '铝', '锂矿', '稀土', '有色', '原油', '煤炭']),
    ('消费', ['消费', '白酒', '茅台', '五粮液', '免税', '旅游', '零售', '家电', '食品', '百货']),
    ('全球市场', ['美联储', '美元', '美股', '纳斯达克', '标普', '道指', '欧洲', '日本', '港股']),
    ('市场动态', ['A股', '沪深', '沪指', '深成指', '创业板', '成交额', '涨停', '跌停', '大盘', '指数', '收盘', '融资余额']),
]

_SENT_POS = ['上调', '增长', '突破', '中标', '增持', '回购', '新高', '扩大', '降准', '降息', '利好', '盈利', '超预期', '获批', '翻倍', '上涨', '净流入', '扩张', '涨停', '提振', '回暖', '创新高']
_SENT_NEG = ['下调', '下跌', '亏损', '减持', '处罚', '违规', '风险', '下滑', '违约', '暴雷', '跌停', '净流出', '萎缩', '承压', '利空', '降级', '立案', '诉讼', '破产', '爆仓', '警示']


def _derive_category(text):
    for cat, kws in _NEWS_CATEGORY_RULES:
        if any(k in text for k in kws):
            return cat
    return '财经快讯'


def _derive_sentiment(text):
    pos = sum(1 for w in _SENT_POS if w in text)
    neg = sum(1 for w in _SENT_NEG if w in text)
    if pos > neg:
        return '利好'
    if neg > pos:
        return '利空'
    return '中性'


def _strip_bracket(s):
    s = (s or '').strip()
    while s.startswith('【') and '】' in s:
        s = s[s.index('】') + 1:].strip()
    return s


def _fetch_cls_news(count=20):
    """拉取财联社电报快讯，返回前端契约格式列表；失败返回 None。"""
    try:
        import requests
    except Exception:
        return None
    try:
        sess = requests.Session()
        sess.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        })
        try:
            sess.get('https://m.cls.cn/telegraph', timeout=10)
        except Exception:
            pass
        params = {'refresh_type': '1', 'rn': str(count), 'app': 'CailianpressWap', 'sv': '1'}
        resp = sess.get('https://m.cls.cn/nodeapi/telegraphs', params=params, timeout=15)
        resp.raise_for_status()
        roll = (resp.json().get('data') or {}).get('roll_data') or []
    except Exception:
        return None
    if not roll:
        return None

    tz = datetime.timezone(datetime.timedelta(hours=8))
    items = []
    for i, row in enumerate(roll):
        if not isinstance(row, dict):
            continue
        title = _strip_bracket(row.get('title') or '')
        content = _strip_bracket(row.get('content') or '')
        brief = _strip_bracket(row.get('brief') or '')
        if not title:
            title = brief or content
        if not title:
            continue
        if len(title) > 40:
            title = title[:40] + '…'
        summary = brief or content
        if not summary:
            summary = title
        try:
            t = datetime.datetime.fromtimestamp(int(row.get('ctime')), tz)
        except Exception:
            t = datetime.datetime.now()
        text = title + ' ' + summary + ' ' + content
        items.append({
            'id': row.get('id') or (i + 1),
            'time': t.strftime('%Y-%m-%d %H:%M'),
            'source': '财联社',
            'category': _derive_category(text),
            'sentiment': _derive_sentiment(text),
            'title': title,
            'summary': summary,
            'content': content or summary,
        })
    items.sort(key=lambda x: x['time'], reverse=True)
    return items


def refresh_news():
    """拉取并更新内存新闻；失败时保留旧数据，仅在无任何可展示数据时才标记错误。"""
    global _news, _news_error
    items = _fetch_cls_news()
    with _news_lock:
        if items:
            _news = items
            _news_error = False
        else:
            _news_error = len(_news) == 0


def get_news():
    with _news_lock:
        return list(_news)


def news_error():
    with _news_lock:
        return _news_error


def get_news_categories():
    return ['全部'] + [c for c, _ in _NEWS_CATEGORY_RULES]

# ============ 回测框架 ============
BACKTEST_FRAMEWORKS = [
    {'id': 'quant', 'name': 'QuantEngine 自研框架', 'desc': '平台内置，支持 Tick 级模拟与 GPU 加速，回测速度最快', 'tag': '推荐'},
    {'id': 'backtrader', 'name': 'Backtrader', 'desc': 'Python 社区经典事件驱动框架，指标库丰富'},
    {'id': 'vnpy', 'name': 'vn.py', 'desc': '国产开源框架，回测与实盘交易接口一体化'},
    {'id': 'zipline', 'name': 'Zipline', 'desc': 'Quantopian 开源引擎，适合美股日频策略研究'},
]

# ============ 投资偏好默认值 ============
# 默认值需与前端 quant-invest-vue/src/lib/constants.js 的 DEFAULT_PREFS 保持一致，修改请同步两边
DEFAULT_PREFS = {
    'risk': '稳健型',
    'horizon': '中线（1-6个月）',
    'sectors': ['新能源', '人工智能', '医药生物'],
    'maxPosition': 25,
    'stopLoss': 8,
    'takeProfit': 30,
    'benchmark': '沪深300',
}

