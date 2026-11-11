# -*- coding: utf-8 -*-
"""共享技术指标：简单均线 / 指数均线 / RSI，供回测引擎与自由构建引擎复用。"""


def sma(values, n):
    out = [None] * len(values)
    s = 0.0
    for i in range(len(values)):
        s += values[i]
        if i >= n:
            s -= values[i - n]
        if i >= n - 1:
            out[i] = s / n
    return out


def ema(values, n):
    out = [None] * len(values)
    k = 2.0 / (n + 1)
    prev = values[0]
    for i in range(len(values)):
        prev = values[0] if i == 0 else values[i] * k + prev * (1 - k)
        out[i] = prev
    return out


def rsi(values, n):
    out = [None] * len(values)
    gain = 0.0
    loss = 0.0
    for i in range(1, len(values)):
        ch = values[i] - values[i - 1]
        gain += max(ch, 0.0)
        loss += max(-ch, 0.0)
        if i > n:
            ch2 = values[i - n] - values[i - n - 1]
            gain -= max(ch2, 0.0)
            loss -= max(-ch2, 0.0)
        if i >= n:
            rs = gain / max(loss, 1e-9)
            out[i] = 100 - 100 / (1 + rs)
    return out