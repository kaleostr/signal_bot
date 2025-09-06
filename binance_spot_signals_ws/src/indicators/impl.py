import numpy as np

def ema(arr: np.ndarray, period: int) -> np.ndarray:
    arr = np.asarray(arr, dtype=float)
    out = np.full_like(arr, np.nan, dtype=float)
    n = arr.size
    if n == 0 or period <= 0:
        return out
    finite_mask = np.isfinite(arr)
    if not finite_mask.any():
        return out
    first = int(np.argmax(finite_mask))
    s = float(arr[first])
    out[first] = s
    alpha = 2.0 / (period + 1.0)
    for i in range(first + 1, n):
        x = arr[i]
        if not np.isfinite(x):
            x = s
        s = alpha * x + (1.0 - alpha) * s
        out[i] = s
    return out

def rsi(close: np.ndarray, period: int=14) -> np.ndarray:
    close = np.asarray(close, dtype=float)
    diff = np.diff(close, prepend=close[0])
    gain = np.where(diff>0, diff, 0.0)
    loss = np.where(diff<0, -diff, 0.0)
    g = np.nanmean(gain[1:period+1]); l = np.nanmean(loss[1:period+1])
    avg_g = np.full_like(close, np.nan, dtype=float)
    avg_l = np.full_like(close, np.nan, dtype=float)
    if period < close.size:
        avg_g[period] = g; avg_l[period] = l
    for i in range(period+1, close.size):
        g = (g*(period-1) + gain[i])/period
        l = (l*(period-1) + loss[i])/period
        avg_g[i] = g; avg_l[i] = l
    rs = avg_g/np.where(avg_l==0, np.nan, avg_l)
    return 100 - (100/(1+rs))

def macd(close: np.ndarray, fast=12, slow=26, signal=9):
    close = np.asarray(close, dtype=float)
    macd_line = ema(close, fast) - ema(close, slow)
    signal_line = ema(macd_line, signal)
    hist = macd_line - signal_line
    return macd_line, signal_line, hist

def atr_rma(high: np.ndarray, low: np.ndarray, close: np.ndarray, period=14) -> np.ndarray:
    high = np.asarray(high, dtype=float)
    low = np.asarray(low, dtype=float)
    close = np.asarray(close, dtype=float)
    prev_close = np.roll(close, 1)
    tr = np.maximum.reduce([high-low, np.abs(high - prev_close), np.abs(low - prev_close)])
    tr[0] = high[0]-low[0]
    out = np.full_like(tr, np.nan, dtype=float)
    v = np.nanmean(tr[1:period+1])
    if period < tr.size:
        out[period] = v
    for i in range(period+1, tr.size):
        v = (v*(period-1) + tr[i])/period
        out[i] = v
    return out

class VWAPSession:
    def __init__(self):
        self.reset()
    def reset(self):
        self.sum_pv = 0.0; self.sum_v = 0.0; self.values = []
    def update(self, price: float, vol: float):
        self.sum_pv += price*vol; self.sum_v += vol; self.values.append(price)
    def vwap(self):
        return self.sum_pv/self.sum_v if self.sum_v>0 else np.nan
    def sigma(self):
        arr = np.array(self.values, dtype=float)
        if arr.size < 2: return (np.nan, np.nan, np.nan, np.nan)
        m = np.nanmean(arr); s = np.nanstd(arr)
        return (m+s, m+2*s, m-s, m-2*s)
