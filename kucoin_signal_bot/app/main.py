import asyncio, os, time, json, re
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
    "started_ts": time.time(),
    "runtime": {"min_confirms": 3}
}

RUNTIME_PATH = "/data/runtime.json"

app = FastAPI()

def load_cfg() -> Dict[str, Any]:

    with open("/app/config.yaml", "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    # allowed keys for syncing to options.json (based on config.json schema)
    try:
        with open('/data/../../kucoin_signal_bot/config.json','r',encoding='utf-8') as cf:
            cjj = json.load(cf)
            schema_keys = list((cjj or {}).get('schema', {}).keys())
            cfg['allowed_keys'] = schema_keys
    except Exception:
        cfg['allowed_keys'] = []
    return cfg

def get_addon_options() -> Dict[str, Any]:
    opts_path = "/data/options.json"
    if os.path.exists(opts_path):
        with open(opts_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def confirms_emoji(confirms: int) -> str:
    return "🟢" if confirms==5 else ("🟡" if confirms==4 else ("🟠" if confirms==3 else ("🔴" if confirms==2 else "⚪")))

def load_runtime_min_confirms(default_val:int) -> int:
    try:
        if os.path.exists(RUNTIME_PATH):
            with open(RUNTIME_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                return int(data.get("min_confirms", default_val))
    except Exception:
        pass
    return default_val


def write_json(path, data):
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False

def read_json(path, default):
    try:
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception:
        pass
    return default

def merge_dicts(a: dict, b: dict) -> dict:
    c = dict(a or {})
    c.update(b or {})
    return c

def merged_options():
    opts = get_addon_options()
    user = read_json('/data/user_config.json', {})
    return merge_dicts(opts, user)

def persist_options(new_vals: dict):
    # Update user_config.json
    user = read_json('/data/user_config.json', {})
    user = merge_dicts(user, new_vals or {})
    write_json('/data/user_config.json', user)
    # Try also update options.json so Supervisor UI reflects changes
    opts = get_addon_options()
    opts = merge_dicts(opts, new_vals or {})
    # Keep only known keys
    allowed = set(STATE['cfg']['allowed_keys']) if STATE.get('cfg') and 'allowed_keys' in STATE['cfg'] else set(opts.keys())
    clean = {k: v for k, v in opts.items() if k in allowed or k in opts}
    write_json('/data/options.json', clean)
def save_runtime_min_confirms(val:int):
    try:
        with open(RUNTIME_PATH, "w", encoding="utf-8") as f:
            json.dump({"min_confirms": int(val)}, f)
    except Exception:
        pass

def adjust_tps(entry: float, raw_levels, opts: Dict[str, Any], spread_bps: float=None):
    fee = int(opts.get("taker_fee_bps",10))
    buffer = int(opts.get("roundtrip_extra_buffer_bps",5))
    min_net = int(opts.get("min_net_profit_bps",10))
    cost_bps = 2*fee + (int(spread_bps) if spread_bps is not None else buffer)
    min_pct = (cost_bps + min_net) / 10000.0
    result = []
    for lvl in raw_levels:
        pct = max(float(lvl), min_pct)
        result.append(entry*(1.0+pct))
    return result

def format_signal(sym: str, res: Dict[str, Any], confirms: int, adjusted_tps):
    entry = res["entry"]; sl = res["sl"]
    emoji = confirms_emoji(confirms)
    reasons = ", ".join(res["reasons"])
    return (f"💵 {sym}\n{emoji} {confirms}/5 | 5m — LONG\n"
            f"Вход: {entry:.6f}\n"
            f"SL:   {sl:.6f}\n"
            f"TP1:  {adjusted_tps[0]:.6f}\nTP2:  {adjusted_tps[1]:.6f}\nTP3:  {adjusted_tps[2]:.6f}\n"
            f"Причины: {reasons}")

async def build_symbol_universe(ku: KucoinClient, quote: str, top_n: int, min_vol24: float):
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

async def fetch_df(ku: KucoinClient, symbol: str, tf: str, opts: Dict[str, Any]):
    kl = await ku.fetch_candles(symbol, tf=tf, limit=300)
    df = ohlcv_df(kl)
    df = add_indicators(df, opts)
    return df

async def scan_once(tg: TelegramNotifier, ku: KucoinClient, cfg: Dict[str, Any], opts: Dict[str, Any]):
    quote = opts.get("symbols_quote","USDT")
    topn = int(opts.get("top_n_by_volume", 120))
    min_vol24 = float(opts.get("min_vol_24h_usd", 5000000))
    symbols = await build_symbol_universe(ku, quote, topn, min_vol24)
    STATE["symbols"] = symbols[:]
    cooldown = int(opts.get("cooldown_minutes", 20)) * 60
    min_conf = STATE["runtime"]["min_confirms"]

    for sym in symbols:
        try:
            df5  = await fetch_df(ku, sym, tf=cfg["timeframes"]["trigger_tf"], opts=opts)
            df15 = await fetch_df(ku, sym, tf=cfg["timeframes"]["setup_tf"],  opts=opts)
            df1h = await fetch_df(ku, sym, tf=cfg["timeframes"]["bias_tf"],   opts=opts)
            if df5.empty or df15.empty or df1h.empty:
                continue

            res = should_signal(df1h, df15, df5, cfg, opts)
            if res.get("ok"):
                confirms = int(res.get("confirms", len(res.get("reasons", []))))
                if confirms < max(3, min_conf):
                    continue

                spread_bps = None
                if bool(opts.get("use_level1_spread", False)):
                    try:
                        lvl1 = await ku.fetch_level1(sym)
                        best_ask = float(lvl1.get("bestAsk", 0)); best_bid = float(lvl1.get("bestBid", 0))
                        if best_ask > 0 and best_bid > 0:
                            spread_bps = int(((best_ask - best_bid) / best_bid) * 10000)
                    except Exception:
                        spread_bps = None

                entry = float(res["entry"])
                adjusted_tps = adjust_tps(entry, cfg["exits"]["tp_levels_pct"], opts, spread_bps)

                now = time.time()
                last = STATE["last_signal_ts"].get(sym, 0)
                last_confirms = STATE["last_confirms"].get(sym, 0)

                if now - last >= cooldown or confirms > last_confirms:
                    msg = format_signal(sym, res, confirms, adjusted_tps)
                    await tg.send(msg)
                    STATE["last_signal_ts"][sym] = now
                    STATE["last_confirms"][sym] = confirms
                    STATE["signals_sent"] += 1
        except Exception:
            continue

async def worker_loop():
    opts = get_addon_options()
    cfg = load_cfg()
    STATE["cfg"] = cfg
    def_val = int(opts.get("min_confirms", 3))
    STATE["runtime"]["min_confirms"] = load_runtime_min_confirms(def_val)

    tg = TelegramNotifier(opts.get("telegram_token",""), opts.get("telegram_chat_id",""))
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
    tg = TelegramNotifier(opts.get("telegram_token",""), opts.get("telegram_chat_id",""))
    while True:
        try:
            updates = await tg.get_updates()
            for upd in updates:
                text = tg.parse_command(upd)
                if not text:
                    continue
                low = text.lower().strip()
                if low == "/ping":
                    await tg.send("pong")
                elif low == "/status":
                    tracked = len(STATE.get("symbols", []))
                    sent = STATE.get("signals_sent", 0)
                    uptime = int(time.time() - STATE.get("started_ts", time.time()))
                    await tg.send(
                        "📊 Status\n"
                        f"Tracked: {tracked}\nSignals sent: {sent}\nUptime: {uptime}s\n"
                        f"min_confirms: {STATE['runtime']['min_confirms']}\n"
                        f"EMA: {opts.get('ema_fast',20)}/{opts.get('ema_mid',50)}/{opts.get('ema_slow',200)}; "
                        f"RSI: {opts.get('rsi_length',14)}; MACD: {opts.get('macd_fast',12)}/{opts.get('macd_slow',26)}/{opts.get('macd_signal',9)}; "
                        f"RVOL15m_min: {opts.get('rvol15m_min',1.6)}"
                    )
                elif low.startswith("/min"):
                    m = re.findall(r"/min\s+(\d+)", low)
                    if m:
                        val = int(m[0])
                        if val in (3,4,5):
                            STATE["runtime"]["min_confirms"] = val
                            save_runtime_min_confirms(val)
                            await tg.send(f"✅ min_confirms установлен: {val}")
                        else:
                            await tg.send("Укажи 3, 4 или 5: /min 4")
                    else:
                        await tg.send("Использование: /min 3|4|5")
        except Exception:
            pass
        await asyncio.sleep(5)

from fastapi import FastAPI
app = FastAPI()


from fastapi.responses import HTMLResponse
from fastapi import Request

def read_json(path, default):
    try:
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception:
        pass
    return default

def merged_options():
    opts = get_addon_options()
    user = read_json('/data/user_config.json', {})
    merged = opts.copy()
    merged.update(user)
    return merged

@app.get("/", response_class=HTMLResponse)
def ui_root():
    with open('/app/ui.html','r',encoding='utf-8') as f:
        return f.read()

@app.get("/api/options")
def api_get_options():
    return merged_options()

@app.post("/api/options")
async def api_set_options(req: Request):
    data = await req.json()
    persist_options(data)
    return {"ok": True}

@app.get("/api/ping")
async def api_ping():
    tg_opts = merged_options()
    tg = TelegramNotifier(tg_opts.get("telegram_token",""), tg_opts.get("telegram_chat_id",""))
    await tg.send("pong")
    return {"ok": True}

@app.get("/api/set_min")
async def api_set_min(val: int):
    if val not in (3,4,5):
        return {"ok": False, "error":"min must be 3/4/5"}
    STATE['runtime']['min_confirms'] = val
    save_runtime_min_confirms(val)
    persist_options({'min_confirms': val})
    tg_opts = merged_options()
    tg = TelegramNotifier(tg_opts.get('telegram_token',''), tg_opts.get('telegram_chat_id',''))
    await tg.send(f"✅ min_confirms set to {val} (via UI)")
    return {"ok": True, "min": val}

@app.on_event("startup")
async def on_startup():
    asyncio.create_task(worker_loop())
    asyncio.create_task(commands_loop())

@app.get("/health")
def health():
    return {"ok": True, "signals_sent": STATE["signals_sent"], "tracked_symbols": len(STATE.get("symbols", [])), "min_confirms": STATE["runtime"]["min_confirms"]}
