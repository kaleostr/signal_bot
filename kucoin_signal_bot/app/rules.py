from typing import Dict, Any, Tuple
import pandas as pd

def rolling_rvol(vol_series: pd.Series, window:int=20) -> float:
    if len(vol_series) < window or vol_series.iloc[-1] == 0:
        return 0.0
    sma = vol_series.rolling(window).mean().iloc[-1]
    if pd.isna(sma) or sma == 0:
        return 0.0
    return float(vol_series.iloc[-1] / sma)

def compute_confirmations(df5: pd.DataFrame, df15: pd.DataFrame, opts: Dict[str, Any]) -> Dict[str,Any]:
    confirms = 0; reasons = []
    if df5["close"].iloc[-1] >= df5["ema20"].iloc[-1]:
        confirms += 1; reasons.append("EMA20 reclaim")
    if df5["close"].iloc[-1] >= df5["vwap"].iloc[-1] and df5["vwap"].diff().iloc[-1] > 0:
        confirms += 1; reasons.append("VWAP↑ & price>VWAP")
    hist = df5["macd_hist"].iloc[-3:]
    d1 = hist.diff().fillna(0).iloc[-1] > 0
    d2 = hist.diff().fillna(0).iloc[-2] > 0 if len(hist) >= 2 else False
    if d1 and d2:
        confirms += 1; reasons.append("MACD impulse")
    rvol15 = rolling_rvol(df15["volume"], window=20)
    if rvol15 >= float(opts.get("rvol15m_min", 1.6)):
        confirms += 1; reasons.append(f"RVOL15m {rvol15:.2f}")
    if df5["close"].iloc[-1] >= df5["high"].iloc[-10:].max():
        confirms += 1; reasons.append("Local high breakout")
    return {"count": confirms, "reasons": reasons, "rvol15m": rvol15}

def anti_noise_checks(df5: pd.DataFrame, opts: Dict[str, Any]) -> bool:
    body = abs(df5["close"].iloc[-1] - df5["open"].iloc[-1])
    atr = df5["atr"].iloc[-1] if not pd.isna(df5["atr"].iloc[-1]) else 0.0
    if atr > 0 and body > float(opts.get("breakout_body_max_atr_mult", 1.8)) * atr:
        return False
    ema200 = df5["ema200"].iloc[-1]
    if ema200 > 0:
        dist = abs(df5["close"].iloc[-1] - ema200) / ema200 * 100
        if dist < float(opts.get("ema200_5m_min_distance_pct", 0.2)):
            return False
    return True

def bias_ok(df1h: pd.DataFrame, df15: pd.DataFrame, opts: Dict[str, Any]) -> bool:
    rsi_min_1h = int(opts.get("rsi_min_1h", opts.get("bias_rsi_min", 50)))
    if df1h["rsi"].iloc[-1] < rsi_min_1h:
        return False
    # basic EMA trend on 1h
    if not (df1h["ema20"].iloc[-1] >= df1h["ema50"].iloc[-1]):
        return False
    return True

def make_sl_tp(entry: float, df5: pd.DataFrame, cfg: Dict[str, Any]) -> Tuple[float, list]:
    atr = float(df5["atr"].iloc[-1]) if not pd.isna(df5["atr"].iloc[-1]) else 0.0
    vwap = float(df5["vwap"].iloc[-1]) if not pd.isna(df5["vwap"].iloc[-1]) else entry
    sl1 = vwap - 0.5*atr
    low_recent = float(df5["low"].iloc[-10:].min()) if len(df5) >= 10 else float(df5["low"].min())
    sl2 = low_recent - 0.5*atr
    sl = max(min(sl1, sl2), 0.0)
    raw = cfg["exits"]["tp_levels_pct"]
    tps = [entry * (1 + x) for x in raw]
    return sl, tps

def should_signal(df1h: pd.DataFrame, df15: pd.DataFrame, df5: pd.DataFrame, cfg: Dict[str, Any], opts: Dict[str, Any]) -> Dict[str, Any]:
    if df5.empty or df15.empty or df1h.empty:
        return {"ok": False, "why": "insufficient data"}
    if not bias_ok(df1h, df15, opts):
        return {"ok": False, "why": "bias filter failed"}
    if not anti_noise_checks(df5, opts):
        return {"ok": False, "why": "anti-noise failed"}
    # optional trigger RSI over (5m)
    rsi_over_5m = int(opts.get("rsi_over_5m", 0))
    if rsi_over_5m and df5["rsi"].iloc[-1] < rsi_over_5m:
        return {"ok": False, "why": f"trigger rsi<{rsi_over_5m}"}
    c = compute_confirmations(df5, df15, opts)
    need = cfg["trigger"]["confirmations_needed"]
    if c["count"] >= need:
        entry = float(df5['close'].iloc[-1])
        sl, tps = make_sl_tp(entry, df5, cfg)
        return {"ok": True, "reasons": c["reasons"], "confirms": c["count"], "entry": entry, "sl": sl, "tps": tps, "rvol15m": c["rvol15m"]}
    return {"ok": False, "why": f"only {c['count']} confirmations"}
