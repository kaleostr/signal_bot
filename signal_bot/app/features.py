from typing import Dict, Any, List, Tuple
import pandas as pd
import numpy as np
from ta.trend import EMAIndicator, MACD
from ta.momentum import RSIIndicator
from ta.volatility import AverageTrueRange

def ohlcv_df(klines: List[List[Any]]) -> pd.DataFrame:
    # KuCoin kline: [time, open, close, high, low, volume, turnover]; time in ms string
    if not klines:
        return pd.DataFrame(columns=["time","open","high","low","close","volume"])
    rows = []
    for k in klines:
        t = int(float(k[0]))  # ms
        rows.append({
            "time": pd.to_datetime(t, unit="ms"),
            "open": float(k[1]),
            "close": float(k[2]),
            "high": float(k[3]),
            "low": float(k[4]),
            "volume": float(k[5]),
        })
    df = pd.DataFrame(rows).sort_values("time").reset_index(drop=True)
    return df

def add_indicators(df: pd.DataFrame, ema_periods=(20,50,200), rsi_len=14, atr_len=14) -> pd.DataFrame:
    if df.empty:
        return df
    for p in ema_periods:
        df[f"ema{p}"] = EMAIndicator(close=df["close"], window=p).ema_indicator()
    macd = MACD(close=df["close"], window_slow=26, window_fast=12, window_sign=9)
    df["macd"] = macd.macd()
    df["macd_signal"] = macd.macd_signal()
    df["macd_hist"] = macd.macd_diff()
    rsi = RSIIndicator(close=df["close"], window=rsi_len)
    df["rsi"] = rsi.rsi()
    atr = AverageTrueRange(high=df["high"], low=df["low"], close=df["close"], window=atr_len)
    df["atr"] = atr.average_true_range()
    # Session VWAP approximation: cum(price*vol)/cum(vol)
    pv = (df["close"] * df["volume"]).cumsum()
    vv = df["volume"].cumsum().replace(0, np.nan)
    df["vwap"] = pv / vv
    return df

def recent(df: pd.DataFrame, n: int = 1) -> pd.Series:
    return df.iloc[-n]

def rolling_rvol(vol_series: pd.Series, window:int=20) -> float:
    if len(vol_series) < window or vol_series.iloc[-1] == 0:
        return 0.0
    sma = vol_series.rolling(window).mean().iloc[-1]
    if not sma or np.isnan(sma) or sma == 0:
        return 0.0
    return float(vol_series.iloc[-1] / sma)

def zscore(series: pd.Series) -> float:
    if len(series) < 20:
        return 0.0
    x = series.dropna().values
    if len(x) < 5:
        return 0.0
    return float((x[-1] - np.mean(x)) / (np.std(x) + 1e-9))

def compute_confirmations(df5: pd.DataFrame, df15: pd.DataFrame, cfg: Dict[str, Any]) -> Dict[str,int]:
    confirms = 0
    reasons = []

    # 1) close above ema20 (5m)
    if cfg["trigger"]["conditions"]["close_above_ema20"]:
        if df5["close"].iloc[-1] >= df5["ema20"].iloc[-1]:
            confirms += 1
            reasons.append("EMA20 reclaim")

    # 2) price above VWAP and VWAP rising
    if cfg["trigger"]["conditions"]["close_above_vwap_and_vwap_rising"]:
        if df5["close"].iloc[-1] >= df5["vwap"].iloc[-1] and df5["vwap"].diff().iloc[-1] > 0:
            confirms += 1
            reasons.append("VWAP↑ & price>VWAP")

    # 3) MACD
    macd_cfg = cfg["trigger"]["conditions"]["macd"]
    if macd_cfg["use"]:
        hist = df5["macd_hist"].iloc[-3:]
        cross_up = df5["macd"].iloc[-1] >= df5["macd_signal"].iloc[-1] and df5["macd"].iloc[-2] < df5["macd_signal"].iloc[-2]
        if (hist.diff().iloc[-1] > 0 and hist.diff().iloc[-2] > 0 and macd_cfg["hist_rising_bars_min"] <= 2) or (macd_cfg["cross_up_allowed"] and cross_up):
            confirms += 1
            reasons.append("MACD impulse")

    # 4) RVOL(15m)
    rvol15 = rolling_rvol(df15["volume"], window=20)
    if rvol15 >= cfg["trigger"]["conditions"]["rvol15m_min"]:
        confirms += 1
        reasons.append(f"RVOL15m {rvol15:.2f}")

    # 5) local high breakout on 5m
    lbars = cfg["trigger"]["conditions"]["broke_local_high_lookback_bars"]
    high_window = df5["high"].iloc[-lbars:]
    if df5["close"].iloc[-1] >= high_window.max():
        confirms += 1
        reasons.append("Local high breakout")

    return {"count": confirms, "reasons": reasons, "rvol15m": rvol15}

def anti_noise_checks(df5: pd.DataFrame, cfg: Dict[str, Any]) -> bool:
    # body size vs ATR
    body = abs(df5["close"].iloc[-1] - df5["open"].iloc[-1])
    atr = df5["atr"].iloc[-1] if not np.isnan(df5["atr"].iloc[-1]) else 0.0
    if atr > 0 and body > cfg["trigger"]["anti_noise"]["breakout_body_max_atr_mult"] * atr:
        return False
    # distance to ema200
    ema200 = df5["ema200"].iloc[-1]
    if ema200 > 0:
        dist = abs(df5["close"].iloc[-1] - ema200) / ema200 * 100
        if dist < cfg["trigger"]["anti_noise"]["ema200_5m_min_distance_pct"]:
            return False
    return True

def bias_ok(df1h: pd.DataFrame, df15: pd.DataFrame, cfg: Dict[str, Any]) -> bool:
    rsi_min = cfg["bias"]["rsi_min"]
    if df1h["rsi"].iloc[-1] < rsi_min:
        # allow override if price above ema200 on 15m
        if cfg["bias"].get("allow_if_price_above_ema200_15m", False):
            return df15["close"].iloc[-1] >= df15["ema200"].iloc[-1]
        return False
    # ema20 >= ema50 (optional)
    if "ema_order" in cfg["bias"] and cfg["bias"]["ema_order"]:
        if not (df1h["ema20"].iloc[-1] >= df1h["ema50"].iloc[-1]):
            return False
    return True
