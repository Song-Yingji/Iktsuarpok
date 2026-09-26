# -*- coding: utf-8 -*-
"""量化后端工具函数：确定性伪随机。"""

MASK32 = 0xFFFFFFFF


def _i32(x):
    """将整数截断为 32 位有符号整数（模拟 JavaScript 位运算语义）。"""
    x &= MASK32
    return x if x < 0x80000000 else x - 0x100000000


def _imul(a, b):
    """模拟 JavaScript Math.imul：32 位有符号整数乘法。"""
    return _i32((a * b) & MASK32)


def hash_seed(s):
    """确定性伪随机数生成器。

    返回一个无参函数，每次调用返回 [0, 1) 的伪随机浮点数。
    同一字符串生成完全相同的随机序列，用于生成稳定的历史 K 线。
    """
    h = _i32(1779033703 ^ len(s))
    for ch in s:
        h = _imul(h ^ ord(ch), 3432918353)
        h = _i32(((h << 13) & MASK32) | ((h & MASK32) >> 19))

    def rnd():
        nonlocal h
        h = _imul(h ^ ((h & MASK32) >> 16), 2246822507)
        h = _imul(h ^ ((h & MASK32) >> 13), 3266489909)
        h = _i32(h ^ ((h & MASK32) >> 16))
        return (h & MASK32) / 4294967296.0

    return rnd