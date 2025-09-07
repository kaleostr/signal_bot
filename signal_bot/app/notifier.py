import asyncio
import httpx
from typing import Optional, List, Dict, Any

class TelegramNotifier:
    def __init__(self, token: str, chat_id: str):
        self.token = token.strip()
        self.chat_id = str(chat_id).strip() if chat_id is not None else ""
        self.base = f"https://api.telegram.org/bot{self.token}" if self.token else None
        self._last_update_id = 0

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

    async def get_updates(self) -> List[Dict[str, Any]]:
        if not self.base:
            return []
        params = {"timeout": 10, "offset": self._last_update_id + 1}
        url = f"{self.base}/getUpdates"
        async with httpx.AsyncClient(timeout=15) as client:
            try:
                r = await client.get(url, params=params)
                data = r.json()
                if not data.get("ok"):
                    return []
                updates = data.get("result", [])
                if updates:
                    self._last_update_id = max(u.get("update_id", 0) for u in updates)
                return updates
            except Exception:
                return []

    @staticmethod
    def parse_command(upd: Dict[str, Any]) -> Optional[str]:
        msg = upd.get("message") or upd.get("edited_message")
        if not msg:
            return None
        text = msg.get("text", "").strip()
        if not text.startswith("/"):
            return None
        return text.split()[0].lower()
