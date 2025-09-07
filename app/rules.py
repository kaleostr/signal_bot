from typing import Dict, Any, Tuple
import pandas as pd
from features import compute_confirmations, anti_noise_checks, bias_ok

def make_sl_tp(entry: float, df5: pd.DataFrame, cfg: Dict[str, Any]) -> Tuple[float, list]:
    # SL: VWAP - 1σ (approx by atr*0.5) OR base low (use recent low - 0.5*ATR)
    atr = float(df5["atr"].iloc[-1]) if not pd.isna(df5["atr"].iloc[-1]) else 0.0
    vwap = float(df5["vwap"].iloc[-1]) if not pd.isna(df5["vwap"].iloc[-1]) else entry
    sl1 = vwap - 0.5*atr
    low_recent = float(df5["low"].iloc[-10:].min()) if len(df5) >= 10 else float(df5["low"].min())
    sl2 = low_recent - 0.5*atr
    sl = max(min(sl1, sl2), 0.0)
    tps = [entry * (1 + x) for x in cfg["exits"]["tp_levels_pct"]]
    return sl, tps

def should_signal(df1h: pd.DataFrame, df15: pd.DataFrame, df5: pd.DataFrame, cfg: Dict[str, Any]) -> Dict[str, Any]:
    if df5.empty or df15.empty or df1h.empty:
        return {"ok": False, "why": "insufficient data"}
    if not bias_ok(df1h, df15, cfg):
        return {"ok": False, "why": "bias filter failed"}
    if not anti_noise_checks(df5, cfg):
        return {"ok": False, "why": "anti-noise failed"}

    c = compute_confirmations(df5, df15, cfg)
    need = cfg["trigger"]["confirmations_needed"]
    if c["count"] >= need:
        entry = float(df5['close'].iloc[-1])
        sl, tps = make_sl_tp(entry, df5, cfg)
        return {
            "ok": True,
            "reasons": c["reasons"],
            "confirms": c["count"],
            "entry": entry,
            "sl": sl,
            "tps": tps,
            "rvol15m": c["rvol15m"]
        }
    return {"ok": False, "why": f"only {c['count']} confirmations"}
