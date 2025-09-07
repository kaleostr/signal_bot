from typing import Dict, Any, List
import pandas as pd
import numpy as np
from ta.trend import EMAIndicator, MACD
from ta.momentum import RSIIndicator
from ta.volatility import AverageTrueRange

# -------- Helpers --------
def _infer_tf_str(df: pd.DataFrame) -> str:
    """Infer timeframe string like '5m', '15m', '1h' from df.time spacing."""
    try:
        if len(df) < 3:
            return "5m"
        dt = (df["time"].iloc[-1] - df["time"].iloc[-2]).total_seconds()
        # closest of 5m/15m/1h by ratio
        candidates = [("5m", 300.0), ("15m", 900.0), ("1h", 3600.0)]
        best = min(candidates, key=lambda x: abs(dt - x[1]))
        return best[0]
    except Exception:
        return "5m"

def _opt(opts: Dict[str, Any], key: str, default=None):
    return opts.get(key, default)

def _tf_key(tf: str, base: str) -> str:
    # base like "ema_fast" -> "ema_fast_5m" etc.
    suf = {"5m":"_5m","15m":"_15m","1h":"_1h"}.get(tf,"")
    return f"{base}{suf}"

def _get_tf_int(opts: Dict[str, Any], tf: str, base: str, default: int) -> int:
    """Per‑TF integer with backward compatible fallback to the legacy global key."""
    v = opts.get(_tf_key(tf, base), None)
    if isinstance(v, (int, float)) and not pd.isna(v):
        return int(v)
    v = opts.get(base, None)
    if isinstance(v, (int, float)) and not pd.isna(v):
        return int(v)
    return int(default)

def _get_tf_float(opts: Dict[str, Any], tf: str, base: str, default: float) -> float:
    v = opts.get(_tf_key(tf, base), None)
    if isinstance(v, (int,float)) and not pd.isna(v):
        return float(v)
    v = opts.get(base, None)
    if isinstance(v, (int,float)) and not pd.isna(v):
        return float(v)
    return float(default)

# -------- Core transforms --------
def ohlcv_df(klines: List[List[Any]]) -> pd.DataFrame:
    """Convert KuCoin kline rows -> tidy DataFrame (time, open, high, low, close, volume)."""
    if not klines:
        return pd.DataFrame(columns=["time","open","high","low","close","volume"])
    rows = []
    for k in klines:
        # KuCoin returns: [time, open, close, high, low, volume, turnover]
        #  time is ms since epoch (string or number)
        t = int(float(k[0]))
        rows.append({
            "time": pd.to_datetime(t, unit="ms"),
            "open": float(k[1]),
            "close": float(k[2]),
            "high": float(k[3]),
            "low":  float(k[4]),
            "volume": float(k[5])
        })
    df = pd.DataFrame(rows).sort_values("time").reset_index(drop=True)
    return df

def _ensure_indicators(df: pd.DataFrame, tf: str, opts: Dict[str, Any]) -> pd.DataFrame:
    """Compute indicators with per‑TF windows + legacy fallback:
       EMA fast/mid/slow, EMA200, VWAP, RSI, MACD, ATR."""
    if df.empty:
        # return empty with expected columns
        for col in ["ema_fast","ema_mid","ema_slow","ema200","vwap","rsi","macd","macd_signal","macd_hist","atr"]:
            df[col] = np.nan
        return df

    # VWAP (sessionless cumulative)
    pv = (df["close"] * df["volume"]).cumsum()
    vv = df["volume"].cumsum().replace(0, np.nan)
    df["vwap"] = pv / vv

    # Windows per TF (fallback to legacy fields if absent)
    ema_fast_w = _get_tf_int(opts, tf, "ema_fast", 20 if tf!="5m" else 9)
    ema_mid_w  = _get_tf_int(opts, tf, "ema_mid",  50 if tf!="5m" else 21)
    ema_slow_w = _get_tf_int(opts, tf, "ema_slow", 200 if tf!="5m" else 50)

    # Core EMA trio
    df["ema_fast"] = EMAIndicator(close=df["close"], window=int(ema_fast_w)).ema_indicator()
    df["ema_mid"]  = EMAIndicator(close=df["close"], window=int(ema_mid_w)).ema_indicator()
    df["ema_slow"] = EMAIndicator(close=df["close"], window=int(ema_slow_w)).ema_indicator()

    # Dedicated EMA200 (used by anti‑noise regardless of 'slow')
    df["ema200"] = EMAIndicator(close=df["close"], window=200).ema_indicator()

    # RSI
    rsi_len = _get_tf_int(opts, tf, "rsi_len", 14 if tf!="5m" else 9)
    df["rsi"] = RSIIndicator(close=df["close"], window=int(rsi_len)).rsi()

    # MACD
    macd_fast = _get_tf_int(opts, tf, "macd_fast", 12 if tf!="5m" else 8)
    macd_slow = _get_tf_int(opts, tf, "macd_slow", 26 if tf!="5m" else 21)
    macd_sig  = _get_tf_int(opts, tf, "macd_signal", 9 if tf!="5m" else 5)
    _macd = MACD(close=df["close"], window_fast=int(macd_fast), window_slow=int(macd_slow), window_sign=int(macd_sig))
    df["macd"] = _macd.macd()
    df["macd_signal"] = _macd.macd_signal()
    df["macd_hist"] = _macd.macd_diff()

    # ATR (14)
    df["atr"] = AverageTrueRange(high=df["high"], low=df["low"], close=df["close"], window=14).average_true_range()

    return df

def add_indicators(df: pd.DataFrame, opts: Dict[str, Any]) -> pd.DataFrame:
    """Public API used by main.py. Infers TF and applies per‑TF windows with fallback."""
    tf = _infer_tf_str(df)
    return _ensure_indicators(df.copy(), tf, opts)

def rolling_rvol(vol_series: pd.Series, window:int=20) -> float:
    """Relative volume (last bar volume / SMA(window))."""
    if len(vol_series) < max(window, 2) or vol_series.iloc[-1] == 0:
        return 0.0
    sma = vol_series.rolling(window).mean().iloc[-1]
    if not sma or np.isnan(sma) or sma == 0:
        return 0.0
    return float(vol_series.iloc[-1] / sma)
