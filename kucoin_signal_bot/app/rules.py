from typing import Dict, Any, Tuple
import pandas as pd

# ---- Setup helpers ----
def _last(df: pd.DataFrame, col: str):
    try:
        return float(df[col].iloc[-1])
    except Exception:
        return float("nan")

def _prev(df: pd.DataFrame, col: str):
    try:
        return float(df[col].iloc[-2])
    except Exception:
        return float("nan")

def _ema_order_ok(df: pd.DataFrame, mode: str) -> bool:
    """mode: 'fast_over_mid' or 'mid_over_slow'"""
    ef = _last(df, "ema_fast"); em = _last(df, "ema_mid"); es = _last(df, "ema_slow")
    if any(pd.isna(x) for x in (ef, em, es)):
        return False
    if mode == "mid_over_slow":
        return em >= es
    return ef >= em  # default

def _macd_hist_rising(df: pd.DataFrame, bars:int=2) -> bool:
    if len(df) < bars+1: return False
    hist = df["macd_hist"].iloc[-(bars+1):].diff().fillna(0.0)
    # last 'bars' diffs must be > 0
    return bool((hist.iloc[-bars:] > 0).all())

def bias_ok(df1h: pd.DataFrame, opts: Dict[str, Any]) -> Tuple[bool, str]:
    """Bias (1h): EMA order, RSI >= min, optional MACD condition."""
    need_order = bool(opts.get("bias_need_ema_order", True))
    order_mode = str(opts.get("bias_ema_order_mode", "fast_over_mid"))
    rsi_min = float(opts.get("rsi_min_1h", opts.get("bias_rsi_min", 50)))
    # macd condition: off | macd_ge_0 | hist_rising
    macd_mode = str(opts.get("bias_macd_condition", "hist_rising"))

    # EMA order
    if need_order and not _ema_order_ok(df1h, order_mode):
        return False, "EMA order (1h) failed"

    # RSI filter
    if _last(df1h, "rsi") < rsi_min:
        return False, f"RSI(1h) < {rsi_min}"

    # Optional MACD check
    if macd_mode == "macd_ge_0":
        if _last(df1h, "macd_hist") < 0 and _last(df1h, "macd") < 0:
            return False, "MACD(1h) < 0"
    elif macd_mode == "hist_rising":
        if not _macd_hist_rising(df1h, bars=int(opts.get("bias_macd_bars_min", 2))):
            return False, "MACD hist not rising (1h)"

    return True, "ok"

def setup_ok(df15: pd.DataFrame, opts: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    """Setup (15m): EMA order + RSI threshold + RVOL >= min."""
    order_mode = str(opts.get("bias_ema_order_mode", "fast_over_mid"))  # reuse mode
    rsi_min_15m = float(opts.get("rsi_min_15m", 50))
    # Relative Volume threshold (window=20)
    window = int(opts.get("rvol_window_15m", 20))
    vol = df15["volume"]
    rvol = 0.0
    if len(vol) >= window:
        sma = vol.rolling(window).mean().iloc[-1]
        if sma and sma > 0:
            rvol = float(vol.iloc[-1] / sma)
    # threshold
    rvol_thresh = float(opts.get("rvol15m_min", 1.6))

    if not _ema_order_ok(df15, order_mode):
        return False, {"why":"EMA order (15m) failed", "rvol": rvol}
    if _last(df15, "rsi") < rsi_min_15m:
        return False, {"why": f"RSI(15m) < {rsi_min_15m}", "rvol": rvol}
    if rvol < rvol_thresh:
        return False, {"why": f"RVOL(15m) {rvol:.2f} < {rvol_thresh}", "rvol": rvol}

    return True, {"rvol": rvol}

def anti_noise_checks(df5: pd.DataFrame, opts: Dict[str, Any]) -> Tuple[bool, str]:
    """ATR cap for breakout body; Min distance to EMA200 (5m)."""
    max_body_mult = float(opts.get("breakout_body_max_atr_mult", 1.8))
    min_dist_pct  = float(opts.get("ema200_5m_min_distance_pct", 0.2))

    # body vs ATR
    body = abs(_last(df5, "close") - _last(df5, "open"))
    atr = _last(df5, "atr")
    if not pd.isna(atr) and atr > 0 and body > max_body_mult * atr:
        return False, "Body too large vs ATR"

    # distance to ema200 (%)
    ema200 = _last(df5, "ema200")
    price = _last(df5, "close")
    if ema200 and ema200 > 0:
        dist_pct = abs(price - ema200) / ema200 * 100.0
        if dist_pct < min_dist_pct:
            return False, "Too close to EMA200 (5m)"
    return True, "ok"

def compute_trigger_confirms(df5: pd.DataFrame, df15: pd.DataFrame, opts: Dict[str, Any]) -> Dict[str, Any]:
    """Return confirmations count and reasons for Trigger (5m)."""
    reasons = []
    # EMA cross/reclaim (5m): fast above mid AND either crossed up this bar OR price reclaimed fast
    ef, pf = _last(df5,"ema_fast"), _prev(df5,"ema_fast")
    em, pm = _last(df5,"ema_mid"),  _prev(df5,"ema_mid")
    pc = _last(df5,"close")

    cross_up = pf < pm and ef >= em
    reclaim = pc >= ef and ef >= em
    if cross_up or reclaim:
        reasons.append("EMA (5m) cross/reclaim")

    # RSI over threshold
    rsi_over = float(opts.get("rsi_over_5m", 55.0))
    if _last(df5, "rsi") >= rsi_over:
        reasons.append(f"RSI≥{int(rsi_over)} (5m)")

    # MACD impulse or cross-up
    macd = _last(df5, "macd"); macds = _last(df5, "macd_signal")
    cross = macd >= macds and _prev(df5,"macd") < _prev(df5,"macd_signal")
    hist_rise = _macd_hist_rising(df5, bars=int(opts.get("macd_hist_rising_bars_min", 1)))
    if cross or hist_rise:
        reasons.append("MACD↑ / cross-up (5m)")

    # VWAP rising and price above VWAP
    vwap = _last(df5,"vwap"); vwap_prev = _prev(df5,"vwap")
    if vwap and vwap_prev and vwap > vwap_prev and pc >= vwap:
        reasons.append("VWAP↑ & price>VWAP")

    return {"count": len(reasons), "reasons": reasons}

def make_sl_tp(entry: float, df5: pd.DataFrame) -> Tuple[float, list]:
    """Basic SL under recent swing/ATR; TPs are placeholders (main.py adjusts)."""
    # SL: min of last 3 lows minus small buffer (0.05%)
    look = min(5, len(df5))
    if look >= 2:
        swing = float(df5["low"].iloc[-look:]).min()
    else:
        swing = entry * 0.997
    atr = _last(df5, "atr")
    buf = 0.5 * (atr if not pd.isna(atr) else entry*0.001)
    sl = min(swing, entry - buf)
    # placeholder TPs (adjusted in main.py with fees/spread):
    tps = [entry * (1.0 + x) for x in [0.007, 0.012, 0.020]]
    return float(sl), [float(x) for x in tps]

def should_signal(df1h: pd.DataFrame, df15: pd.DataFrame, df5: pd.DataFrame, cfg: Dict[str, Any], opts: Dict[str, Any]) -> Dict[str, Any]:
    """Full rule pipeline: Bias(1h) → Setup(15m) → Trigger(5m) + Anti‑Noise."""
    if any(d is None or d.empty for d in (df1h, df15, df5)):
        return {"ok": False, "why": "insufficient data"}

    ok, why = bias_ok(df1h, opts)
    if not ok:
        return {"ok": False, "why": f"bias: {why}"}

    ok_s, ctx = setup_ok(df15, opts)
    if not ok_s:
        return {"ok": False, "why": f"setup: {ctx.get('why','failed')}"}

    ok_n, why_n = anti_noise_checks(df5, opts)
    if not ok_n:
        return {"ok": False, "why": f"anti-noise: {why_n}"}

    trig = compute_trigger_confirms(df5, df15, opts)
    need = int(opts.get("min_confirms", cfg.get("trigger", {}).get("confirmations_needed", 3)))

    if trig["count"] >= need:
        entry = float(df5["close"].iloc[-1])
        sl, tps = make_sl_tp(entry, df5)
        return {
            "ok": True,
            "reasons": trig["reasons"],
            "confirms": trig["count"],
            "entry": entry,
            "sl": sl,
            "tps": tps,
            "rvol15m": float(ctx.get("rvol", 0.0))
        }
    return {"ok": False, "why": f"only {trig['count']} confirmations"}
