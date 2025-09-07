from typing import Dict, Any, Tuple, List
import pandas as pd
from features import rolling_rvol

def compute_confirmations(df5: pd.DataFrame, df15: pd.DataFrame, opts: Dict[str, Any]) -> Dict[str,Any]:
    confirms = 0; reasons = []
    if df5["close"].iloc[-1] >= df5["ema20"].iloc[-1]:
        confirms += 1; reasons.append("EMA20 reclaim")
    if df5["close"].iloc[-1] >= df5["vwap"].iloc[-1] and df5["vwap"].diff().iloc[-1] > 0:
        confirms += 1; reasons.append("VWAP↑ & price>VWAP")
    hist = df5["macd_hist"].iloc[-3:]
    cross_up_allowed = bool(opts.get("macd_cross_up_allowed", True))
    cross_up = (df5["macd"].iloc[-1] >= df5["macd_signal"].iloc[-1]) and (df5["macd"].iloc[-2] < df5["macd_signal"].iloc[-2])
    rising_need = int(opts.get("macd_hist_rising_bars_min", 2))
    d1 = hist.diff().fillna(0).iloc[-1] > 0
    d2 = hist.diff().fillna(0).iloc[-2] > 0 if len(hist) >= 2 else False
    rising_ok = (d1 and d2) if rising_need >= 2 else d1
    if rising_ok or (cross_up_allowed and cross_up):
        confirms += 1; reasons.append("MACD impulse")
    rvol15 = rolling_rvol(df15["volume"], window=20)
    if rvol15 >= float(opts.get("rvol15m_min", 1.6)):
        confirms += 1; reasons.append(f"RVOL15m {rvol15:.2f}")
    lbars = int(opts.get("breakout_lookback_bars", 10))
    if df5["close"].iloc[-1] >= df5["high"].iloc[-lbars:].max():
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
    if df1h["rsi"].iloc[-1] < int(opts.get("bias_rsi_min", 50)):
        if bool(opts.get("bias_allow_price_above_ema200_15m", True)):
            return df15["close"].iloc[-1] >= df15["ema200"].iloc[-1]
        return False
    if bool(opts.get("bias_need_ema_order", True)):
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


# ---- Adaptive Take Profit calculation ----
def _parse_float_list(val, default_list):
    if val is None:
        return default_list
    if isinstance(val, (int, float)):
        return [float(val)]
    if isinstance(val, list):
        out = []
        for v in val:
            try: out.append(float(v))
            except: pass
        return out or default_list
    if isinstance(val, str):
        parts = [p.strip() for p in val.split(",")]
        out = []
        for p in parts:
            if not p: continue
            try: out.append(float(p))
            except: pass
        return out or default_list
    return default_list

def _recent_highs(df: pd.DataFrame, windows: List[int]):
    highs = []
    for w in windows:
        w = int(max(2, w))
        if len(df) >= w:
            highs.append(float(df["high"].iloc[-w:].max()))
    highs = sorted(set([h for h in highs if not pd.isna(h)]))
    return highs

def _clean_targets(entry: float, ts: list):
    seen = set(); out = []
    for t in ts or []:
        try: t = float(t)
        except: continue
        if pd.isna(t) or t <= entry: continue
        key = round(t, 8)
        if key in seen: continue
        seen.add(key); out.append(t)
    out = sorted(out)[:3]
    return out if out else [entry*1.007, entry*1.012, entry*1.02]

def make_sl_tp(entry: float, df5: pd.DataFrame, opts: Dict[str, Any] = None) -> Tuple[float, list]:
    # Stop: swing low +/- ATR buffer
    look = min(5, len(df5))
    if look >= 2:
        swing = float(df5["low"].iloc[-look:].min())
    else:
        swing = entry * 0.997
    atr = _last(df5, "atr")
    buf = 0.5 * (atr if not pd.isna(atr) else entry*0.001)
    sl = min(swing, entry - buf)
    sl = max(sl, 1e-7)

    mode = str((opts or {}).get("tp_mode", "fixed")).lower()

    if mode == "fixed":
        raw = (opts or {}).get("tp_levels_pct")
        levels = _parse_float_list(raw, [0.007, 0.012, 0.020])
        ts = [entry * (1.0 + max(0.0001, lv)) for lv in levels]
        return float(sl), _clean_targets(entry, ts)

    if mode == "atr_mult":
        m = _parse_float_list((opts or {}).get("atr_tp_mults", [1.0,1.5,2.0]), [1.0,1.5,2.0])
        a = atr if not pd.isna(atr) and atr and atr > 0 else entry*0.004
        ts = [entry + k*a for k in m]
        return float(sl), _clean_targets(entry, ts)

    if mode == "r_multiple":
        R = max(entry - sl, entry*0.001)
        mults = _parse_float_list((opts or {}).get("r_multiples", [1.0,1.5,2.0]), [1.0,1.5,2.0])
        ts = [entry + n*R for n in mults]
        return float(sl), _clean_targets(entry, ts)

    if mode == "bb_upper":
        mavg = _last(df5, "bb_mavg"); hband = _last(df5, "bb_hband")
        if not pd.isna(mavg) and not pd.isna(hband):
            bb_dev = float((opts or {}).get("bb_dev", 2.0))
            stdev = abs(hband - mavg) / max(1e-9, bb_dev)
            devs = _parse_float_list((opts or {}).get("bb_tp_devs", [2.0,2.5,3.0]), [2.0,2.5,3.0])
            ts = [mavg + d*stdev for d in devs]
        else:
            ts = [entry*1.01, entry*1.015, entry*1.02]
        return float(sl), _clean_targets(entry, ts)

    if mode == "ema_target":
        target = str((opts or {}).get("ema_tp_target", "ema200")).lower()
        ema = _last(df5, "ema200") if target == "ema200" else _last(df5, "ema_mid")
        offsets = _parse_float_list((opts or {}).get("ema_tp_offsets_bps", [0,5,10]), [0,5,10])
        if not pd.isna(ema) and ema and ema > 0:
            ts = [ema * (1.0 + float(bps)/10000.0) for bps in offsets]
        else:
            ts = [entry*1.008, entry*1.013, entry*1.02]
        return float(sl), _clean_targets(entry, ts)

    if mode == "structure":
        looks = _parse_float_list((opts or {}).get("structure_lookbacks", [20,50,100]), [20,50,100])
        looks = [int(max(5, w)) for w in looks]
        highs = _recent_highs(df5, looks)
        ts = highs
        return float(sl), _clean_targets(entry, ts)

    # fallback to fixed
    raw = (opts or {}).get("tp_levels_pct")
    levels = _parse_float_list(raw, [0.007, 0.012, 0.020])
    ts = [entry * (1.0 + max(0.0001, lv)) for lv in levels]
    return float(sl), _clean_targets(entry, ts)



def should_signal(df1h: pd.DataFrame, df15: pd.DataFrame, df5: pd.DataFrame, cfg: Dict[str, Any], opts: Dict[str, Any]) -> Dict[str, Any]:
    if df5.empty or df15.empty or df1h.empty:
        return {"ok": False, "why": "insufficient data"}
    if not bias_ok(df1h, df15, opts):
        return {"ok": False, "why": "bias filter failed"}
    if not anti_noise_checks(df5, opts):
        return {"ok": False, "why": "anti-noise failed"}
    c = compute_confirmations(df5, df15, opts)
    need = cfg["trigger"]["confirmations_needed"]
    if c["count"] >= need:
        entry = float(df5['close'].iloc[-1])
        sl, tps = make_sl_tp(entry, df5, cfg)
        return {"ok": True, "reasons": c["reasons"], "confirms": c["count"], "entry": entry, "sl": sl, "tps": tps, "rvol15m": c["rvol15m"]}
    return {"ok": False, "why": f"only {c['count']} confirmations"}
