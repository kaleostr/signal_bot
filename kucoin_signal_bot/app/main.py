import asyncio, os, time, json, re, yaml
from typing import Dict, Any
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
import httpx

from kucoin_client import KucoinClient
from features import ohlcv_df, add_indicators
from rules import should_signal
from notifier import TelegramNotifier

SUP_URL = "http://supervisor"
SUP_TOKEN = os.environ.get("SUPERVISOR_TOKEN","")

STATE = {"signals_sent":0,"last_signal_ts":{},"last_confirms":{},"symbols":[],"cfg":None,"started_ts":time.time(),"runtime":{"min_confirms":3}}
RUNTIME_PATH = "/data/runtime.json"

app = FastAPI()

ALLOWED_SCHEMA_KEYS = {"telegram_token","telegram_chat_id","min_vol_24h_usd","cooldown_minutes","timezone","symbols_quote","top_n_by_volume","min_confirms"}

def merged_options():
    user = read_json('/data/user_config.json', {})
    opts = merged_options()
    return merge_dicts(opts, user)

def filter_schema_keys(d: dict) -> dict:
    return {k: v for k, v in (d or {}).items() if k in ALLOWED_SCHEMA_KEYS}


def get_addon_options() -> Dict[str, Any]:
    # Prefer supervisor API if available
    if SUP_TOKEN:
        try:
            r = httpx.get(f"{SUP_URL}/addons/self/info", headers={"Authorization": f"Bearer {SUP_TOKEN}"}, timeout=5.0)
            if r.status_code == 200:
                info = r.json()
                opts = (info.get("data",{}) or {}).get("options", {}) or {}
                if opts:
                    return opts
        except Exception:
            pass
    # fallback to local file
    try:
        with open("/data/options.json","r",encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def write_json(path, data):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False

def read_json(path, default):
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return default

def merge_dicts(a: dict, b: dict) -> dict:
    c = dict(a or {}); c.update(b or {}); return c

def load_cfg() -> Dict[str, Any]:
    with open("/app/config.yaml","r",encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    return cfg

def load_runtime_min_confirms(default_val:int) -> int:
    try:
        if os.path.exists(RUNTIME_PATH):
            with open(RUNTIME_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                return int(data.get("min_confirms", default_val))
    except Exception: pass
    return default_val

def save_runtime_min_confirms(val:int):
    try:
        with open(RUNTIME_PATH, "w", encoding="utf-8") as f:
            json.dump({"min_confirms": int(val)}, f)
    except Exception: pass

async def supervisor_set_options(new_opts: dict):
    if not SUP_TOKEN:
        return False
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            payload = {"options": new_opts}
            r = await c.post(f"{SUP_URL}/addons/self/options", headers={"Authorization": f"Bearer {SUP_TOKEN}"}, json=payload)
            return r.status_code == 200
    except Exception:
        return False

def confirms_emoji(n:int)->str:
    return "🟢" if n==5 else ("🟡" if n==4 else ("🟠" if n==3 else ("🔴" if n==2 else "⚪")))

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
    df = add_indicators(df, opts, tf_tag=tf)
    return df

def adjust_tps(entry: float, raw_levels, opts: Dict[str, Any], spread_bps: float=None):
    fee = int(opts.get("taker_fee_bps",10))
    buffer = int(opts.get("roundtrip_extra_buffer_bps",5))
    min_net = int(opts.get("min_net_profit_bps",10))
    cost_bps = 2*fee + (int(spread_bps) if spread_bps is not None else buffer)
    min_pct = (cost_bps + min_net) / 10000.0
    return [entry*max(1.0+x, 1.0+min_pct) for x in raw_levels]

def format_signal(sym: str, res: Dict[str, Any], confirms: int, adjusted_tps):
    entry = res["entry"]; sl = res["sl"]
    reasons = ", ".join(res["reasons"])
    emoji = confirms_emoji(confirms)
    return (f"💵 {sym}\n{emoji} {confirms}/5 | 5m — LONG\n"
            f"Вход: {entry:.6f}\nSL:   {sl:.6f}\nTP1:  {adjusted_tps[0]:.6f}\nTP2:  {adjusted_tps[1]:.6f}\nTP3:  {adjusted_tps[2]:.6f}\n"
            f"Причины: {reasons}")

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
            df5  = await fetch_df(ku, sym, "5m", opts)
            df15 = await fetch_df(ku, sym, "15m", opts)
            df1h = await fetch_df(ku, sym, "1h", opts)
            if df5.empty or df15.empty or df1h.empty:
                continue

            res = should_signal(df1h, df15, df5, cfg, opts)
            if res.get("ok"):
                confirms = int(res.get("confirms", 0))
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
                    await tg.send(format_signal(sym, res, confirms, adjusted_tps))
                    STATE["last_signal_ts"][sym] = now
                    STATE["last_confirms"][sym] = confirms
                    STATE["signals_sent"] += 1
        except Exception:
            continue

async def worker_loop():
    opts = merged_options()
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
    opts = merged_options()
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
                        f"min_confirms: {STATE['runtime']['min_confirms']}"
                    )
                elif low.startswith("/min"):
                    import re as _re
                    m = _re.findall(r"/min\s+(\d+)", low)
                    if m:
                        val = int(m[0])
                        if val in (3,4,5):
                            STATE["runtime"]["min_confirms"] = val
                            save_runtime_min_confirms(val)
                            # push to supervisor options too
                            cur = get_addon_options()
                            cur["min_confirms"] = val
                            await supervisor_set_options(cur)
                            await tg.send(f"✅ min_confirms set to {val}")
                        else:
                            await tg.send("Use: /min 3|4|5")
                    else:
                        await tg.send("Use: /min 3|4|5")
        except Exception:
            pass
        await asyncio.sleep(5)

@app.on_event("startup")
async def on_startup():
    asyncio.create_task(worker_loop())
    asyncio.create_task(commands_loop())

@app.get("/", response_class=HTMLResponse)
def ui_root():
    with open('/app/ui.html','r',encoding='utf-8') as f:
        return f.read()

@app.get("/api/options")
def api_get_options():
    user = read_json('/data/user_config.json', {})
    opts = merged_options()
    return merge_dicts(opts, user)

@app.post("/api/options")
async def api_set_options(req: Request):
    data = await req.json()
    # persist to user_config and supervisor
    user = read_json('/data/user_config.json', {})
    user = merge_dicts(user, data or {})
    write_json('/data/user_config.json', user)
    opts = merged_options()
    newopts = merge_dicts(opts, data or {})
    await supervisor_set_options(filter_schema_keys(newopts))
    return {"ok": True}

@app.get("/api/ping")
async def api_ping():
    opts = merged_options()
    tg = TelegramNotifier(opts.get("telegram_token",""), opts.get("telegram_chat_id",""))
    await tg.send("pong")
    return {"ok": True}

@app.get("/api/set_min")
async def api_set_min(val: int):
    if val not in (3,4,5):
        return {"ok": False, "error":"min must be 3/4/5"}
    STATE["runtime"]["min_confirms"] = val
    save_runtime_min_confirms(val)
    opts = merged_options()
    opts["min_confirms"] = val
    await supervisor_set_options(opts)
    tg = TelegramNotifier(opts.get("telegram_token",""), opts.get("telegram_chat_id",""))
    await tg.send(f"✅ min_confirms set to {val} (via UI)")
    return {"ok": True, "min": val}

@app.get("/health")
def health():
    return {"ok": True, "signals_sent": STATE["signals_sent"], "tracked_symbols": len(STATE.get("symbols", [])), "min_confirms": STATE["runtime"]["min_confirms"]}
