# KuCoin Spot Signal Bot — v0.3.0

Home Assistant add-on that scans KuCoin spot (USDT pairs) and sends Telegram alerts.
Logic: **Bias (1h) → Setup (15m) → Trigger (5m)** with **per-timeframe indicators**.

## Features
- Top-by-volume scanning with liquidity filter.
- Confirmation score (3–5) → 🟠/🟡/🟢 messages in Telegram.
- Fee/spread-aware TP (optional Level1 spread).
- Web UI (dark) with sections: Basics, Signal Strength, Bias 1h, Setup 15m, Trigger 5m, Anti-Noise, Exits.
- Telegram commands: /ping, /status, /min 3|4|5. Startup message on boot.

## Install
1) Add your GitHub repository to HA Add-on Store (⋮ → Repositories).
2) Install **KuCoin Spot Signal Bot** and start it.

## Configuration (HA → Configuration)
Basic fields only:
- telegram_token, telegram_chat_id
- min_confirms
- min_vol_24h_usd, cooldown_minutes
- symbols_quote, top_n_by_volume
- timezone

> All indicator settings live in the Web UI at :8080 (Open Web UI).

## Per‑TF Defaults
- 1h: EMA 20/50/200, RSI len 14 min 50, MACD 12/26/9
- 15m: EMA 20/50/200, RSI len 14 min 50, MACD 12/26/9, RVOL 1.6
- 5m: EMA 9/21/50,  RSI len 9 over 55, MACD 8/21/5
