# KuCoin Spot Signal Bot (Home Assistant Add-on)

**Версия:** 0.1.2

Сканер USDT-пар на споте KuCoin, выдаёт сигналы в Telegram по сетапу **Bias (1H) → Setup (15m) → Trigger (5m)**.
Добавлено: умный кулдаун, команды `/ping` и `/status`, цветовые статусы (5🟢, 4🟡, 3🟠; 2🔴 подавляется).

## Установка через ваш GitHub-репозиторий
1. Убедитесь, что в корне репозитория есть `repository.json` (этот файл уже в архиве).
2. Папка аддона: `kucoin_signal_bot/` (этот архив уже содержит нужную структуру).
3. В Home Assistant → **Add-on Store → Repositories** добавьте ссылку на ваш GitHub.

## Настройки аддона
- `telegram_token` — токен бота из @BotFather  
- `telegram_chat_id` — ваш chat id (число)  
- `min_vol_24h_usd` — фильтр по ликвидности (по умолчанию 5,000,000)  
- `cooldown_minutes` — пауза между сигналами по одному символу (по умолчанию 20)  
- `symbols_quote` — котируемая валюта (USDT)  
- `top_n_by_volume` — сколько топ-пар мониторить (по умолчанию 120)

## Цветовая шкала подтверждений
- **5/5 → 🟢** (очень сильный)
- **4/5 → 🟡** (сильный)
- **3/5 → 🟠** (средний, базовый порог)
- **2/5 → 🔴** (слабый) — **не отправляется**

## Команды Telegram
- `/ping` — проверка связи (ответ: `pong`)
- `/status` — статус сканера: Tracked, Signals sent, Uptime

## Сообщение сигнала (пример)
```
💵 ENA-USDT
🟡 4/5 | 5m — LONG
Вход: 0.738600
SL:   0.730717
TP1:  0.741554
TP2:  0.744509
TP3:  0.748202
Причины: EMA20 reclaim, VWAP↑ & price>VWAP, MACD impulse, Local high breakout
```
