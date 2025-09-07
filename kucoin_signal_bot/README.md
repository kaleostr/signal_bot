# KuCoin Spot Signal Bot — Home Assistant Add-on

**Version:** 0.2.3  
Dark web UI • Per-timeframe (1h / 15m / 5m) settings • Backward-compatible fallbacks

## What's new (0.2.3)
- Fix: consolidated and minimized add-on options/schema to reduce Supervisor warnings on fresh installs.
- Docs: clear migration note to reset config after upgrade if you see schema warnings.
- Includes all 0.2.2 changes: per‑TF parameters in UI, Bias/Setup/Trigger rules, anti-noise, improved UX.

## Features
- UI-only per-timeframe settings (keeps HA configuration compact):
  - **Bias (1h):** `ema_fast_1h`, `ema_mid_1h`, `ema_slow_1h`, `rsi_len_1h`, `rsi_min_1h`, `macd_fast_1h`, `macd_slow_1h`, `macd_signal_1h`, plus options:
    - `bias_need_ema_order` (default: true)
    - `bias_ema_order_mode`: `fast_over_mid` | `mid_over_slow` (default: `fast_over_mid`)
    - `bias_macd_condition`: `hist_rising` | `macd_ge_0` | `off` (default: `hist_rising`)
  - **Setup (15m):** EMA trio, RSI len/min, MACD 12/26/9, `rvol15m_min` (1.6).
  - **Trigger (5m):** EMA 9/21/50, RSI9 over 55, MACD 8/21/5; VWAP↑ & price>VWAP.
- Anti-noise: ATR body cap, minimum distance to EMA200 (5m).
- Exits: decimal TP levels (e.g., `0.007, 0.012, 0.020`), taker fee bps, extra buffer.
- Backward compatible: if a per‑TF value is not set, falls back to legacy global keys.

## Default recommendations
- **1h:** EMA 20/50/200, RSI14 min 50, MACD 12/26/9  
- **15m:** EMA 20/50/200, RSI14 min 50, MACD 12/26/9, RVOL 1.6  
- **5m:** EMA 9/21/50, RSI9 over 55, MACD 8/21/5

## Install / Update
1. Copy this repo as a custom repository into Home Assistant **Add-on Store** and install (or update) the add-on.
2. Open the add-on **Web UI** → fill out sections **Basics**, **Signal Strength**, **Bias/Setup/Trigger**, **Anti-Noise**, **Exits & Costs** → **Save & Apply**.
3. Health: check `/health` endpoint in the UI footer status (Tracked, Signals, min confirmations).

### Migration note (schema warnings)
If after update Supervisor shows warnings like _"Option 'xxx' does not exist in the schema"_:  
- These are **not critical**. They appear if your stored add-on configuration still has keys that were removed from the schema.  
- To clear them: open **Add-on → Configuration → RESET to defaults** (or manually remove the extra keys).  
- All per-timeframe parameters live in `user_config.json` (UI-only), not in `options.json`.

## Development
- Python files compile-tested with `py_compile`.
- UI: single `ui.html` (dark theme), no external build step.
- Server exposes minimal endpoints: `/api/options`, `/api/set_min`, `/api/ping`, `/health`.

## License
MIT
