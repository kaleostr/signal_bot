from __future__ import annotations
import logging, math
from typing import Dict, List, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import numpy as np
from zoneinfo import ZoneInfo

from src.indicators.impl import ema, macd, rsi, atr_rma, VWAPSession

log = logging.getLogger("engine")

@dataclass
class Series:
    t: List[int] = field(default_factory=list)
    o: List[float] = field(default_factory=list)
    h: List[float] = field(default_factory=list)
    l: List[float] = field(default_factory=list)
    c: List[float] = field(default_factory=list)
    v: List[float] = field(default_factory=list)
    def append(self, k):
        self.t.append(k["t"]); self.o.append(k["o"]); self.h.append(k["h"]); self.l.append(k["l"]); self.c.append(k["c"]); self.v.append(k["v"])
    def arrays(self):
        return (np.array(self.t), np.array(self.o), np.array(self.h), np.array(self.l), np.array(self.c), np.array(self.v))

def local_level_breakout(high: np.ndarray, low: np.ndarray, lookback:int=10)->Tuple[float,float]:
    if high.size < lookback+2: return (np.nan, np.nan)
    res = np.max(high[-(lookback+2):-2])
    sup = np.min(low[-(lookback+2):-2])
    return (res, sup)

class SignalEngine:
    def __init__(self, tz: ZoneInfo, vwap_reset_local: str, cooldown_minutes: int, min_count: int,
                 tick_size: Dict[str,float], telegram,
                 long_only: bool=True, one_signal_per_bar: bool=True,
                 rsi1h_block: int=50, upper_wick_atr_block: float=0.6,
                 ema_fast_1h: int=20, ema_slow_1h: int=50, ema_200_15m: int=200,
                 macd_fast: int=12, macd_slow: int=26, macd_signal: int=9,
                 rsi_period: int=14, rsi_zone_low: int=40, rsi_zone_mid: int=50, rsi_zone_high: int=60,
                 atr_period: int=14, atr_sl_mult: float=1.3,
                 vol_sma_period: int=20, volume_spike_mult: float=1.5,
                 supertrend_enabled: bool=False, supertrend_period: int=10, supertrend_multiplier: float=3.0,
                 tp_multipliers=(0.5,1.0,1.5), atr_trailing_mult: float=0.8, use_vwap_trailing: bool=True,
                 symbol_overrides: dict | None = None):
        self.tz = tz
        self.vwap_hour, self.vwap_minute = map(int, vwap_reset_local.split(":"))
        self.cooldown = timedelta(minutes=cooldown_minutes)
        self.min_count = max(1, min(5, int(min_count)))
        self.tick = tick_size
        self.tg = telegram

        self.h1: Dict[str,Series] = {}
        self.m15: Dict[str,Series] = {}
        self.m5: Dict[str,Series] = {}
        self.vwap: Dict[str,VWAPSession] = {}
        self.last_sent: Dict[str, datetime] = {}
        self.last_bar_sent: Dict[str, int] = {}

        self.long_only = bool(long_only)
        self.one_signal_per_bar = bool(one_signal_per_bar)
        self.rsi1h_block = int(rsi1h_block)
        self.upper_wick_atr_block = float(upper_wick_atr_block)

        self.ema_fast_1h = ema_fast_1h; self.ema_slow_1h = ema_slow_1h; self.ema_200_15m = ema_200_15m
        self.macd_fast = macd_fast; self.macd_slow = macd_slow; self.macd_signal = macd_signal
        self.rsi_period = rsi_period
        self.rsi_low = rsi_zone_low; self.rsi_mid = rsi_zone_mid; self.rsi_high = rsi_zone_high
        self.atr_period = atr_period; self.atr_sl_mult = atr_sl_mult
        self.vol_sma_period = vol_sma_period; self.vol_spike_mult = volume_spike_mult
        self.supertrend_enabled = supertrend_enabled
        self.supertrend_period = supertrend_period; self.supertrend_multiplier = supertrend_multiplier
        self.tp_multipliers = tuple(tp_multipliers)
        self.atr_trailing_mult = float(atr_trailing_mult)
        self.use_vwap_trailing = bool(use_vwap_trailing)
        self.symbol_overrides = symbol_overrides or {}

    def warmup(self, sym: str, h1: List[dict], m15: List[dict], m5: List[dict]):
        self.h1[sym] = Series(); self.m15[sym] = Series(); self.m5[sym] = Series()
        for k in h1: self.h1[sym].append(k)
        for k in m15: self.m15[sym].append(k)
        for k in m5: self.m5[sym].append(k)
        self.vwap[sym] = VWAPSession()
        for k in m5:
            if self._is_same_kst_day(k["t"]):
                tp = (k["h"]+k["l"]+k["c"])/3
                self.vwap[sym].update(tp, k["v"])

    def on_close(self, sym: str, interval: str, k: dict):
        if interval == "1h": self.h1[sym].append(k)
        elif interval == "15m": self.m15[sym].append(k)
        elif interval == "5m":
            self.m5[sym].append(k)
            if self._is_session_reset(k["t"]): self.vwap[sym].reset()
            tp = (k["h"]+k["l"]+k["c"])/3; self.vwap[sym].update(tp, k["v"])

    def _is_same_kst_day(self, ts:int)->bool:
        dt = datetime.fromtimestamp(ts, self.tz); now = datetime.now(self.tz)
        return dt.date() == now.date()

    def _is_session_reset(self, ts:int)->bool:
        dt = datetime.fromtimestamp(ts, self.tz)
        return dt.hour==self.vwap_hour and dt.minute==self.vwap_minute

    def _round(self, sym:str, price:float)->float:
        step = self.tick.get(sym, 0.0001)
        prec = max(0, -int(round(math.log10(step))))
        return round(round(price/step)*step, prec)

    # ---- helpers ----
    def _reclaim(self, series_c: np.ndarray, baseline: np.ndarray, bars_below: int = 3) -> bool:
        if series_c.size < bars_below + 2: return False
        below = np.less(series_c[-(bars_below+1):-1], baseline[-(bars_below+1):-1]).all()
        return bool(below and (series_c[-1] > baseline[-1]))

    def _volume_spike(self, v: np.ndarray, period: int, mult: float) -> bool:
        N = min(period, v.size)
        if N < 2: return False
        sma = np.nanmean(v[-N:])
        return bool(v[-1] > mult * sma)

    def _upper_wick_over_atr(self, o,h,l,c, atr: np.ndarray, thr: float) -> bool:
        if not np.isfinite(atr[-1]) or atr[-1] <= 0: return False
        upper_wick = float(h[-1] - max(o[-1], c[-1]))
        return bool((upper_wick / atr[-1]) > thr)

    # ---- evaluate LONG-only ----
    def evaluate(self, sym: str)->str|None:
        t,o,h,l,c,v = self.m5[sym].arrays()
        if len(c) < 60: return None

        # один сигнал на бар
        last_ts = int(t[-1])
        if self.one_signal_per_bar and self.last_bar_sent.get(sym) == last_ts:
            return None

        # пер-символьные оверрайды
        ov = self.symbol_overrides.get(sym, {})
        confirmations_min = int(ov.get("confirmations_min", self.min_count))
        volume_mult = float(ov.get("volume_spike_mult", self.vol_spike_mult))
        atr_sl_mult = float(ov.get("atr_sl_mult", self.atr_sl_mult))
        require_macd_and_rsi = bool(ov.get("require_macd_and_rsi", False))

        # индикаторы
        c1h = self.h1[sym].arrays()[4]
        c15 = self.m15[sym].arrays()[4]
        ema20_h1 = ema(c1h, self.ema_fast_1h); ema50_h1 = ema(c1h, self.ema_slow_1h)
        ema200_15 = ema(c15, self.ema_200_15m)
        macd_line, macd_sig, macd_hist = macd(c, self.macd_fast, self.macd_slow, self.macd_signal)
        rsi5 = rsi(c, self.rsi_period); rsi15 = rsi(c15, self.rsi_period); rsi1h = rsi(c1h, self.rsi_period)
        atr = atr_rma(h,l,c, self.atr_period)

        # VWAP session
        vwap_val = self.vwap[sym].vwap()
        s1p, s2p, s1n, s2n = self.vwap[sym].sigma()

        # ---- блок-фильтры ----
        if np.isfinite(rsi1h[-1]) and rsi1h[-1] < self.rsi1h_block:
            return None
        if np.isfinite(vwap_val) and np.isfinite(s2p) and c[-1] > s2p:
            touched = any((l[-i] <= s1p) or (l[-i] <= vwap_val) for i in range(1, min(6, len(c))))
            if not touched: return None
        if self._upper_wick_over_atr(o,h,l,c, atr, self.upper_wick_atr_block):
            return None

        above_vwap_now = (np.isfinite(vwap_val) and c[-1] >= vwap_val)
        vwap_reclaim = False
        if np.isfinite(vwap_val) and len(c) >= 5:
            below_cnt = int(np.less(c[-5:-1], vwap_val).sum())
            vwap_reclaim = (below_cnt >= 3 and c[-1] > vwap_val and self._volume_spike(v, self.vol_sma_period, volume_mult))
        if not (above_vwap_now or vwap_reclaim):
            return None

        # ---- группы условий ----
        cond_bias_ema_1h = bool(ema20_h1[-1] > ema50_h1[-1])
        cond_ema200_15m_above = bool(c[-1] > ema200_15[-1])
        cond_ema200_15m_reclaim = self._reclaim(c, ema200_15, bars_below=3)
        cond_trend = cond_bias_ema_1h or cond_ema200_15m_above or cond_ema200_15m_reclaim

        cond_macd_up = bool((macd_hist[-2] <= 0 < macd_hist[-1]) or (macd_hist[-1] > macd_hist[-2] and macd_hist[-2] > macd_hist[-3]))
        cond_macd_up = cond_macd_up and (macd_line[-1] > macd_sig[-1])
        cond_rsi_reclaim50 = bool(rsi5[-1] >= 50 or (rsi5[-3] <= 40 and rsi5[-2] > rsi5[-3] and rsi5[-1] > 50))
        cond_rsi_reclaim50 = cond_rsi_reclaim50 and (rsi15[-1] >= 50)
        cond_momentum = (cond_macd_up and cond_rsi_reclaim50) if require_macd_and_rsi else (cond_macd_up or cond_rsi_reclaim50)

        cond_vwap_above = bool(above_vwap_now or vwap_reclaim)
        cond_volume_spike = self._volume_spike(v, self.vol_sma_period, volume_mult)
        cond_liquidity = cond_vwap_above or cond_volume_spike

        candidates = [
            cond_bias_ema_1h,
            (cond_ema200_15m_above or cond_ema200_15m_reclaim),
            cond_macd_up,
            cond_rsi_reclaim50,
            cond_vwap_above,
            cond_volume_spike
        ]
        selected = candidates[:5]
        ok_cnt = sum(bool(x) for x in selected)
        groups_ok = (cond_trend and cond_momentum and cond_liquidity)
        if not (groups_ok and ok_cnt >= confirmations_min):
            return None

        entry = max(h[-1], c[-1]) * 1.0001
        R = atr[-1] * atr_sl_mult
        sl = entry - R
        tp1 = entry + 0.5 * R
        tp2 = entry + 1.0 * R
        tp3 = entry + 1.5 * R

        trail_atr = c[-1] - 0.8 * atr[-1]
        trail_vwap = vwap_val if np.isfinite(vwap_val) else trail_atr
        trail = max(trail_atr, trail_vwap)

        entry = self._round(sym, entry); sl = self._round(sym, sl)
        tp1 = self._round(sym, tp1); tp2 = self._round(sym, tp2); tp3 = self._round(sym, tp3)
        trail = self._round(sym, trail)

        reasons = []
        if cond_bias_ema_1h: reasons.append("Bias1h EMA20>50")
        if cond_ema200_15m_above: reasons.append("Цена>EMA200(15m)")
        if cond_ema200_15m_reclaim: reasons.append("EMA200(15m) reclaim")
        if cond_macd_up: reasons.append("MACD↑")
        if cond_rsi_reclaim50: reasons.append("RSI5m>50 (+15m≥50)")
        if cond_vwap_above: reasons.append("VWAP↑/reclaim")
        if cond_volume_spike: reasons.append(f"Объём>SMA×{volume_mult:g}")

        msg = (f"🟢 {confirmations_min}/5 | {sym} 5m — LONG\n"
               f"Вход: {entry}\nSL: {sl}\nTP1: {tp1} | TP2: {tp2} | TP3: {tp3}\n"
               f"Trail: ближний к цене → {trail}\n"
               f"Причины: {', '.join(reasons)}")

        now = datetime.now(timezone.utc)
        key = f"{sym}:LONG"
        last = self.last_sent.get(key)
        if last and (now - last) < self.cooldown:
            return None
        self.last_sent[key] = now
        self.last_bar_sent[sym] = last_ts
        return msg

    def status_snapshot(self, symbols: List[str], tz_name: str)->str:
        out = [f"Symbols: {symbols}", f"TZ: {tz_name}", f"Mode: LONG-only",
               f"Min confirmations: {self.min_count}/5",
               f"RSI1h block: < {self.rsi1h_block}",
               f"Cooldown: {self.cooldown}"]
        return "Status:\n" + "\n".join(out)
