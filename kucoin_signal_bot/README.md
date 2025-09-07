# KuCoin Spot Signal Bot — v0.2.1 (stable)

Home Assistant add-on that scans KuCoin spot (USDT pairs) and sends Telegram alerts.
Logic: **Bias (1h) → Setup (15m) → Trigger (5m)**. Dark Web UI with quick 3/4/5 toggle.

## Install
Add this repo to HA Add-on Store, install and start **KuCoin Spot Signal Bot**.

## Configuration (HA → Configuration)
Basic fields only:
- telegram_token, telegram_chat_id
- min_confirms
- min_vol_24h_usd, cooldown_minutes
- symbols_quote, top_n_by_volume
- timezone

**All advanced settings** (indicators, exits, anti-noise) are in the Web UI (:8080).

## Web UI
- Sections: Basics, Signal Strength, Indicators, Trend Filters, Breakout & Momentum, Anti-Noise, Exits & Costs.
- Buttons: **Save & Apply**, **Ping**, quick **3/4/5** (highlighted).
- Telegram commands: `/ping`, `/status`, `/min 3|4|5`.
- On startup: Telegram message “✅ Bot started”.


---
## v0.2.2-fix
- UI-only per-timeframe settings (1h/15m/5m).
- Fixed: no recursion in `merged_options()`; safe merge of HA options + UI config.
- Fixed: `rules.py` keeps local `rolling_rvol` helper (no invalid import).
