import httpx
from typing import Dict, Any, List
KU_PUBLIC = "https://api.kucoin.com"

TF_MAP = {
    "5m": "5min",
    "15m": "15min",
    "1h": "1hour",
}

class KucoinClient:
    def __init__(self):
        self._http = httpx.AsyncClient(timeout=15)

    async def fetch_all_tickers(self) -> Dict[str, Any]:
        url = f"{KU_PUBLIC}/api/v1/market/allTickers"
        r = await self._http.get(url)
        r.raise_for_status()
        return r.json()

    async def fetch_candles(self, symbol: str, tf: str, limit: int = 300) -> List[List[Any]]:
        tftag = TF_MAP.get(tf, tf)
        url = f"{KU_PUBLIC}/api/v1/market/candles"
        params = {"symbol": symbol, "type": tftag}
        r = await self._http.get(url, params=params)
        r.raise_for_status()
        data = r.json().get("data", [])
        data = list(reversed(data))[:limit]
        return data

    async def close(self):
        await self._http.aclose()
