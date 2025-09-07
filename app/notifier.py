import asyncio
import httpx
from typing import Optional

class TelegramNotifier:
    def __init__(self, token: str, chat_id: str):
        self.token = token
        self.chat_id = chat_id
        self.base = f"https://api.telegram.org/bot{self.token}" if token else None

    async def send(self, text: str) -> Optional[dict]:
        if not self.base or not self.chat_id:
            return None
        url = f"{self.base}/sendMessage"
        payload = {"chat_id": self.chat_id, "text": text}
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(url, json=payload)
            try:
                return r.json()
            except Exception:
                return None
