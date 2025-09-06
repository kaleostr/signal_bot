import json, asyncio, logging
from typing import List, AsyncGenerator, Dict
import httpx, websockets

log = logging.getLogger("exchange")

class BinanceREST:
    def __init__(self, base: str):
        self.client = httpx.AsyncClient(base_url=base, timeout=20.0)

    async def get_klines(self, symbol: str, interval: str, limit: int):
        r = await self.client.get("/api/v3/klines", params={"symbol": symbol, "interval": interval, "limit": limit})
        r.raise_for_status()
        out = []
        for it in r.json():
            out.append({
                "t": int(it[6])//1000,
                "o": float(it[1]), "h": float(it[2]), "l": float(it[3]), "c": float(it[4]),
                "v": float(it[5])
            })
        return out

    async def get_tick_size_map(self, symbols: List[str]) -> Dict[str,float]:
        r = await self.client.get("/api/v3/exchangeInfo")
        r.raise_for_status()
        data = r.json()
        set_syms = set(symbols)
        tick = {}
        for s in data.get("symbols", []):
            name = s.get("symbol")
            if name not in set_syms:
                continue
            step = 0.0001
            for f in s.get("filters", []):
                if f.get("filterType") == "PRICE_FILTER":
                    step = float(f["tickSize"]); break
            tick[name] = step
        for name in symbols:
            tick.setdefault(name, 0.0001)
        return tick

class BinanceWS:
    def __init__(self, base: str, symbols: List[str]):
        self.base = base.rstrip("/"); self.symbols = symbols
    def _combined_url(self) -> str:
        streams = []
        for s in self.symbols:
            ls = s.lower()
            streams += [f"{ls}@kline_1h", f"{ls}@kline_15m", f"{ls}@kline_5m"]
        joined = "/".join(streams)
        if self.base.endswith("/stream"):
            return f"{self.base}?streams={joined}"
        else:
            return f"{self.base}/stream?streams={joined}"
    async def stream(self) -> AsyncGenerator[dict, None]:
        url = self._combined_url()
        while True:
            try:
                async with websockets.connect(url, ping_interval=20, ping_timeout=20, close_timeout=5) as ws:
                    log.info("WS connected: %s", url)
                    async for msg in ws:
                        data = json.loads(msg)
                        k = data.get("data", {}).get("k")
                        if not k or not k.get("x"):
                            continue
                        yield {
                            "type": "kline_close",
                            "symbol": k["s"],
                            "interval": k["i"],
                            "kline": {
                                "t": int(k["T"])//1000,
                                "o": float(k["o"]), "h": float(k["h"]), "l": float(k["l"]), "c": float(k["c"]),
                                "v": float(k["v"])
                            }
                        }
            except Exception as e:
                log.warning("WS error: %s — reconnect in 3s", e)
                await asyncio.sleep(3)
