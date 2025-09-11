import httpx
from typing import Dict, Any, List

BN_PUBLIC = "https://api.binance.com"

# Map to Binance intervals 1:1
TF_MAP = {"5m":"5m","15m":"15m","1h":"1h"}

class KucoinClient:  # kept name for compatibility
    def __init__(self):
        self._http = httpx.AsyncClient(timeout=15)

    @staticmethod
    def _to_dash(sym: str) -> str:
        # "SOLUSDT" -> "SOL-USDT"
        if sym.endswith("USDT"):
            base = sym[:-4]
            return f"{base}-USDT"
        return sym

    @staticmethod
    def _to_binance(sym_dash: str) -> str:
        # "SOL-USDT" -> "SOLUSDT"
        return sym_dash.replace("-", "")

    async def fetch_all_tickers(self) -> Dict[str, Any]:
        # Binance 24hr tickers for all symbols
        r = await self._http.get(f"{BN_PUBLIC}/api/v3/ticker/24hr")
        r.raise_for_status()
        arr = r.json()
        # Build KuCoin-like shape used by the app
        tickers = []
        for t in arr:
            sym = t.get("symbol","")
            if not sym.endswith("USDT"):
                continue
            try:
                vol_quote = float(t.get("quoteVolume", "0"))
            except Exception:
                vol_quote = 0.0
            tickers.append({"symbol": self._to_dash(sym), "volValue": str(vol_quote)})
        return {"data": {"ticker": tickers}}

    async def fetch_candles(self, symbol: str, tf: str, limit: int = 300) -> List[List[Any]]:
        # Convert to Binance symbol
        bsym = self._to_binance(symbol)
        interval = TF_MAP.get(tf, tf)
        params = {"symbol": bsym, "interval": interval, "limit": limit}
        r = await self._http.get(f"{BN_PUBLIC}/api/v3/klines", params=params)
        r.raise_for_status()
        data = r.json()
        # Reformat to the order used by features.ohlcv_df:
        # [time, open, close, high, low, volume]
        out = []
        for k in data:
            # Binance kline: [openTime, open, high, low, close, volume, closeTime, ...]
            open_time = k[0]
            open_p = k[1]; high = k[2]; low = k[3]; close = k[4]; vol = k[5]
            out.append([open_time, open_p, close, high, low, vol])
        return out

    async def fetch_level1(self, symbol: str) -> Dict[str, Any]:
        bsym = self._to_binance(symbol)
        r = await self._http.get(f"{BN_PUBLIC}/api/v3/ticker/bookTicker", params={"symbol": bsym})
        r.raise_for_status()
        d = r.json()
        return {
            "bestBid": d.get("bidPrice", "0"),
            "bestAsk": d.get("askPrice", "0")
        }

    async def close(self):
        await self._http.aclose()
