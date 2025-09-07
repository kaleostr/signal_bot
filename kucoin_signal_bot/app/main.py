import asyncio, os, time
from typing import Dict, Any, List
import yaml
import pandas as pd
from fastapi import FastAPI
from kucoin_client import KucoinClient
from features import ohlcv_df, add_indicators
from rules import should_signal
from notifier import TelegramNotifier

STATE = {
    "signals_sent": 0,
    "last_signal_ts": {},
    "last_confirms": {},
    "symbols": [],
    "cfg": None,
    "started_ts": time.time()
}

app = FastAPI()

def load_cfg() -> Dict[str, Any]:
    with open("/app/config.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def get_addon_options() -> Dict[str, Any]:
    opts_path = "/data/options.json"
    if os.path.exists(opts_path):
        import json
        with open(opts_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "telegram_token": os.getenv("TELEGRAM_TOKEN",""),
        "telegram_chat_id": os.getenv("TELEGRAM_CHAT_ID",""),
        "min_vol_24h_usd": 5000000,
        "cooldown_minutes": 20,
        "timezone": "Asia/Seoul",
        "symbols_quote": "USDT",
        "top_n_by_volume": 120
    }

def confirms_emoji(confirms: int) -> str:
    if confirms == 5:
        return "🟢"
    if confirms == 4:
        return "🟡"
    if confirms == 3:
        return "🟠"
    if confirms == 2:
        return "🔴"
    return "⚪"

def format_signal(sym: str, res: Dict[str, Any]) -> str:
    entry = res["entry"]
    sl = res["sl"]
    tps = res["tps"]
    reasons = ", ".join(res["reasons"])
    confirms = int(res.get("confirms", len(res.get("reasons", []))))
    emoji = confirms_emoji(confirms)
    return (
        f"💵 {sym}\n"
        f"{emoji} {confirms}/5 | 5m — LONG\n"
        f"Вход: {entry:.6f}\n"
        f"SL:   {sl:.6f}\n"
        f"TP1:  {tps[0]:.6f}\n"
        f"TP2:  {tps[1]:.6f}\n"
        f"TP3:  {tps[2]:.6f}\n"
        f"Причины: {reasons}"
    )

async def build_symbol_universe(ku: KucoinClient, quote: str, top_n: int, min_vol24: float) -> List[str]:
    data = await ku.fetch_all_tickers()
    arr = data.get("data", {}).get("ticker", [])
    rows = []
    for t in arr:
        sym = t.get("symbol", "")
        if not sym.endswith(f"-{quote}"):
            continue
        try:
            vol_usd = float(t.get("volValue", "0"))
        except Exception:
            vol_usd = 0.0
        rows.append((sym, vol_usd))
    rows.sort(key=lambda x: x[1], reverse=True)
    rows = [s for s,v in rows if v >= min_vol24][:top_n]
    return rows

async def fetch_df(ku: KucoinClient, symbol: str, tf: str) -> pd.DataFrame:
    kl = await ku.fetch_candles(symbol, tf=tf, limit=300)
    df = ohlcv_df(kl)
    df = add_indicators(df, ema_periods=(20,50,200), rsi_len=14, atr_len=14)
    return df

async def scan_once(tg: TelegramNotifier, ku: KucoinClient, cfg: Dict[str, Any], opts: Dict[str, Any]):
    symbols = await build_symbol_universe(
        ku, opts.get("symbols_quote","USDT"),
        int(opts.get("top_n_by_volume", 120)),
        float(opts.get("min_vol_24h_usd", 5000000))
    )
    STATE["symbols"] = symbols[:]
    cooldown = int(opts.get("cooldown_minutes", 20)) * 60

    for sym in symbols:
        try:
            df5 = await fetch_df(ku, sym, tf=cfg["timeframes"]["trigger_tf"])
            df15 = await fetch_df(ku, sym, tf=cfg["timeframes"]["setup_tf"])
            df1h = await fetch_df(ku, sym, tf=cfg["timeframes"]["bias_tf"])
            if df5.empty or df15.empty or df1h.empty:
                continue

            res = should_signal(df1h, df15, df5, cfg)
            if res.get("ok"):
                now = time.time()
                last = STATE["last_signal_ts"].get(sym, 0)
                last_confirms = STATE["last_confirms"].get(sym, 0)
                new_confirms = int(res.get("confirms", len(res.get("reasons", []))))

                # Suppress 2/5 and below
                if new_confirms < 3:
                    continue

                # Smart cooldown: send if stronger OR cooldown expired
                if now - last >= cooldown or new_confirms > last_confirms:
                    msg = format_signal(sym, res)
                    await tg.send(msg)
                    STATE["last_signal_ts"][sym] = now
                    STATE["last_confirms"][sym] = new_confirms
                    STATE["signals_sent"] += 1
        except Exception:
            continue

async def worker_loop():
    opts = get_addon_options()
    cfg = load_cfg()
    STATE["cfg"] = cfg
    tg = TelegramNotifier(opts["telegram_token"], opts["telegram_chat_id"])
    ku = KucoinClient()

    await tg.send("✅ KuCoin Spot Signal Bot запущен")

    while True:
        try:
            await scan_once(tg, ku, cfg, opts)
            await asyncio.sleep(60)
        except Exception:
            await asyncio.sleep(10)

async def commands_loop():
    opts = get_addon_options()
    tg = TelegramNotifier(opts["telegram_token"], opts["telegram_chat_id"])
    while True:
        try:
            updates = await tg.get_updates()
            for upd in updates:
                cmd = tg.parse_command(upd)
                if not cmd:
                    continue
                if cmd == "/ping":
                    await tg.send("pong")
                elif cmd == "/status":
                    tracked = len(STATE.get("symbols", []))
                    sent = STATE.get("signals_sent", 0)
                    uptime = int(time.time() - STATE.get("started_ts", time.time()))
                    await tg.send(f"📊 Status\nTracked: {tracked}\nSignals sent: {sent}\nUptime: {uptime}s")
        except Exception:
            pass
        await asyncio.sleep(5)

@app.on_event("startup")
async def on_startup():
    asyncio.create_task(worker_loop())
    asyncio.create_task(commands_loop())

@app.get("/health")
def health():
    return {
        "ok": True,
        "signals_sent": STATE["signals_sent"],
        "tracked_symbols": len(STATE.get("symbols", []))
    }
