import asyncio, logging, yaml
from pydantic import BaseModel
from zoneinfo import ZoneInfo
from typing import List, Optional
from src.core.exchange import BinanceREST, BinanceWS
from src.logic.engine import SignalEngine
from src.telegram.notify import Telegram

class Config(BaseModel):
    symbols: List[str]
    timezone: str = "Asia/Seoul"
    vwap_session_reset: str = "00:00"
    cooldown_minutes_per_symbol: int = 10
    one_signal_per_bar: bool = True
    send_startup_message: bool = True
    log_level: str = "INFO"
    long_only: bool = True

    preset: str = "balanced"
    confirmations_min: int = 3
    rsi1h_block: int = 50
    volume_spike_mult: float = 1.5
    upper_wick_atr_block: float = 0.6

    ema_fast_1h: int = 20
    ema_slow_1h: int = 50
    ema_200_15m: int = 200
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    rsi_period: int = 14
    rsi_zone_low: int = 40
    rsi_zone_mid: int = 50
    rsi_zone_high: int = 60
    atr_period: int = 14
    vol_sma_period: int = 20

    atr_sl_mult: float = 1.3
    tp_multipliers: List[float] = [0.5, 1.0, 1.5]
    atr_trailing_mult: float = 0.8
    use_vwap_trailing: bool = True

    tg_token: Optional[str] = None
    tg_chat_id: Optional[str] = None
    symbol_overrides: dict = {}

def _apply_preset(cfg: Config) -> None:
    p = (cfg.preset or "balanced").lower()
    if p == "conservative":
        cfg.confirmations_min = 4
        cfg.rsi1h_block = 55
        cfg.volume_spike_mult = 1.6
        cfg.cooldown_minutes_per_symbol = 12
    elif p == "active":
        cfg.confirmations_min = 2
        cfg.rsi1h_block = 48
        cfg.volume_spike_mult = 1.3
        cfg.cooldown_minutes_per_symbol = 6
    else:
        cfg.confirmations_min = 3
        cfg.rsi1h_block = 50
        cfg.volume_spike_mult = 1.5
        cfg.cooldown_minutes_per_symbol = max(cfg.cooldown_minutes_per_symbol, 10)

async def main(config_path: str):
    with open(config_path, "r") as f:
        cfg = Config(**yaml.safe_load(f))
    _apply_preset(cfg)

    logging.basicConfig(level=getattr(logging, cfg.log_level.upper(), logging.INFO),
                        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
    tz = ZoneInfo(cfg.timezone)
    rest = BinanceREST("https://api.binance.com")
    tick_size = await rest.get_tick_size_map(cfg.symbols)

    token = (cfg.tg_token or "").strip() or None
    chat = (cfg.tg_chat_id or "").strip() or None
    tg = Telegram(token=token, chat_id=chat).fallback_from_env()

    engine = SignalEngine(
        tz=tz,
        vwap_reset_local=cfg.vwap_session_reset,
        cooldown_minutes=cfg.cooldown_minutes_per_symbol,
        min_count=cfg.confirmations_min,
        tick_size=tick_size,
        telegram=tg,
        long_only=cfg.long_only,
        one_signal_per_bar=cfg.one_signal_per_bar,
        rsi1h_block=cfg.rsi1h_block,
        upper_wick_atr_block=cfg.upper_wick_atr_block,
        ema_fast_1h=cfg.ema_fast_1h,
        ema_slow_1h=cfg.ema_slow_1h,
        ema_200_15m=cfg.ema_200_15m,
        macd_fast=cfg.macd_fast, macd_slow=cfg.macd_slow, macd_signal=cfg.macd_signal,
        rsi_period=cfg.rsi_period,
        rsi_zone_low=cfg.rsi_zone_low, rsi_zone_mid=cfg.rsi_zone_mid, rsi_zone_high=cfg.rsi_zone_high,
        atr_period=cfg.atr_period, atr_sl_mult=cfg.atr_sl_mult,
        vol_sma_period=cfg.vol_sma_period, volume_spike_mult=cfg.volume_spike_mult,
        tp_multipliers=cfg.tp_multipliers, atr_trailing_mult=cfg.atr_trailing_mult,
        use_vwap_trailing=cfg.use_vwap_trailing,
        symbol_overrides=cfg.symbol_overrides
    )

    # Warmup
    for s in cfg.symbols:
        h1 = await rest.get_klines(s, "1h", 300)
        m15 = await rest.get_klines(s, "15m", 300)
        m5 = await rest.get_klines(s, "5m", 300)
        engine.warmup(s, h1, m15, m5)

    if cfg.send_startup_message and tg.available:
        await tg.send(f"✅ Bot started (TZ={cfg.timezone}). LONG-only. Symbols={cfg.symbols}. Min={cfg.confirmations_min}/5")

    if tg.available:
        asyncio.create_task(tg.poll_commands(lambda: engine.status_snapshot(cfg.symbols, cfg.timezone)))

    ws = BinanceWS("wss://stream.binance.com:9443", cfg.symbols)
    async for event in ws.stream():
        if event["type"] == "kline_close":
            sym = event["symbol"]; interval = event["interval"]; k = event["kline"]
            engine.on_close(sym, interval, k)
            if interval == "5m":
                msg = engine.evaluate(sym)
                if msg:
                    await tg.send(msg)

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    args = parser.parse_args()
    asyncio.run(main(args.config))
