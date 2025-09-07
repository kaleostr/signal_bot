from typing import Dict, Any, List
import pandas as pd
import numpy as np
from ta.trend import EMAIndicator, MACD
from ta.momentum import RSIIndicator
from ta.volatility import AverageTrueRange

def ohlcv_df(klines: List[List[Any]]) -> pd.DataFrame:
    if not klines:
        return pd.DataFrame(columns=["time","open","high","low","close","volume"])
    rows = []
    for k in klines:
        t = int(float(k[0]))
        rows.append({"time": pd.to_datetime(t, unit="ms"),
                     "open": float(k[1]), "close": float(k[2]),
                     "high": float(k[3]), "low": float(k[4]),
                     "volume": float(k[5])})
    return pd.DataFrame(rows).sort_values("time").reset_index(drop=True)

def add_indicators(df: pd.DataFrame, opts: Dict[str, Any]) -> pd.DataFrame:
    if df.empty:
        return df
    efast = int(opts.get("ema_fast",20)); emid = int(opts.get("ema_mid",50)); eslow = int(opts.get("ema_slow",200))
    for p in (efast, emid, eslow):
        df[f"ema{p}"] = EMAIndicator(close=df["close"], window=p).ema_indicator()
    macd = MACD(close=df["close"],
                window_slow=int(opts.get("macd_slow",26)),
                window_fast=int(opts.get("macd_fast",12)),
                window_sign=int(opts.get("macd_signal",9)))
    df["macd"] = macd.macd(); df["macd_signal"] = macd.macd_signal(); df["macd_hist"] = macd.macd_diff()
    rsi_len = int(opts.get("rsi_length",14))
    df["rsi"] = RSIIndicator(close=df["close"], window=rsi_len).rsi()
    atr = AverageTrueRange(high=df["high"], low=df["low"], close=df["close"], window=14)
    df["atr"] = atr.average_true_range()
    pv = (df["close"] * df["volume"]).cumsum(); vv = df["volume"].cumsum().replace(0, np.nan)
    df["vwap"] = pv / vv
    if "ema20" not in df:  df["ema20"]  = EMAIndicator(close=df["close"], window=20).ema_indicator()
    if "ema50" not in df:  df["ema50"]  = EMAIndicator(close=df["close"], window=50).ema_indicator()
    if "ema200" not in df: df["ema200"] = EMAIndicator(close=df["close"], window=200).ema_indicator()
    return df

def rolling_rvol(vol_series: pd.Series, window:int=20) -> float:
    if len(vol_series) < window or vol_series.iloc[-1] == 0:
        return 0.0
    sma = vol_series.rolling(window).mean().iloc[-1]
    if not sma or np.isnan(sma) or sma == 0:
        return 0.0
    return float(vol_series.iloc[-1] / sma)
