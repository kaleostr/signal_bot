import os, httpx, asyncio, logging
from typing import Optional, Callable

log = logging.getLogger("telegram")

class Telegram:
    def __init__(self, token: Optional[str], chat_id: Optional[str]):
        self.token = token
        self.chat_id = chat_id
        self.last_update_id = None
    def fallback_from_env(self):
        if not self.token:
            self.token = os.getenv("TG_TOKEN")
        if not self.chat_id:
            self.chat_id = os.getenv("TG_CHAT_ID")
        return self
    @property
    def available(self)->bool:
        return bool(self.token and self.chat_id)
    async def send(self, text: str):
        if not self.available:
            return
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        async with httpx.AsyncClient(timeout=15.0) as c:
            r = await c.post(url, json={"chat_id": self.chat_id, "text": text})
            try:
                r.raise_for_status()
            except Exception as e:
                log.warning("TG send failed: %s | %s", e, r.text)
    async def poll_commands(self, get_status: Callable[[], str]):
        if not self.token:
            return
        base = f"https://api.telegram.org/bot{self.token}/getUpdates"
        while True:
            try:
                params = {"timeout": 20}
                if self.last_update_id is not None:
                    params["offset"] = self.last_update_id + 1
                async with httpx.AsyncClient(timeout=30.0) as c:
                    r = await c.get(base, params=params)
                    r.raise_for_status()
                    data = r.json()
                    for upd in data.get("result", []):
                        self.last_update_id = upd["update_id"]
                        msg = upd.get("message") or {}
                        if str(msg.get("chat", {}).get("id")) != str(self.chat_id):
                            continue
                        text = (msg.get("text") or "").strip().lower()
                        if text == "/ping":
                            await self.send("pong")
                        elif text == "/status":
                            await self.send(get_status())
            except Exception as e:
                log.debug("TG polling error: %s", e)
            await asyncio.sleep(5)
