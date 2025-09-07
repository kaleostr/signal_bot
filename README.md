# KuCoin Spot Signal Bot — Home Assistant Add-on

**Версия:** 0.2.5  
Пер‑таймфрейм настройки (1h / 15m / 5m), тёмный Web UI, гибкая логика Bias→Setup→Trigger, анти‑шум и удобные выходы.

---

## Что нового

### 0.2.5
- Схема конфига стала толерантнее: убрали строгую валидацию `tp_levels_pct` из `schema`, чтобы апдейты не падали из‑за разных форматов (строка или список). Уведомление от Supervisor о лишнем ключе можно просто игнорировать или удалить ключ из конфигурации аддона.
- Остальные ключи схемы сохранены, чтобы не было ворнингов на «легаси»-параметры.

### 0.2.4
- Расширили `schema`/`options` и добавили дефолты для всех часто встречающихся ключей (в т.ч. легаси) — Supervisor перестаёт ругаться на «Option ... not in the schema».

### 0.2.3
- Привели схему к минимально достаточной и добавили README.  
- Миграционные заметки по сбросу конфига, если видите предупреждения.

### 0.2.2
- Добавлен тёмный Web UI с отдельными секциями **Bias 1h / Setup 15m / Trigger 5m / Anti‑Noise / Exits & Costs**.  
- Пер‑TF параметры стали **UI‑only** и не захламляют `options.json`.  
- Переписана логика правил и расчёт индикаторов с фоллбеком на старые ключи.

---

## Возможности
- **Пер‑TF параметры (UI‑only)**:  
  - **Bias (1h):** `ema_fast_1h`, `ema_mid_1h`, `ema_slow_1h`, `rsi_len_1h`, `rsi_min_1h`, `macd_fast_1h`, `macd_slow_1h`, `macd_signal_1h`, а также:
    - `bias_need_ema_order` (по умолч. `true`)
    - `bias_ema_order_mode`: `fast_over_mid` | `mid_over_slow` (по умолч. `fast_over_mid`)
    - `bias_macd_condition`: `hist_rising` | `macd_ge_0` | `off` (по умолч. `hist_rising`)
  - **Setup (15m):** EMA trio, RSI len/min, MACD 12/26/9, `rvol15m_min` (1.6).
  - **Trigger (5m):** EMA 9/21/50, RSI9 over 55, MACD 8/21/5, VWAP↑ & price>VWAP.
- **Анти‑шум:** лимит тела пробоя `ATR×mult`, минимальная дистанция до EMA200 (5m).  
- **Выходы и издержки:** TP‑уровни в **десятичном виде** (`0.007, 0.012, 0.020`), `taker_fee_bps`, дополнительный буфер.  
- **Фоллбек:** если пер‑TF значение не задано — берутся старые общие ключи (`ema_fast`, `ema_mid`, `ema_slow`, `rsi_length`, `macd_*`).

### Дефолт‑рекомендации
- **1h:** EMA 20/50/200, RSI14 min 50, MACD 12/26/9  
- **15m:** EMA 20/50/200, RSI14 min 50, MACD 12/26/9, RVOL 1.6  
- **5m:** EMA 9/21/50, RSI9 over 55, MACD 8/21/5

---

## Установка / Обновление
1. Добавьте репозиторий кастомных аддонов в Home Assistant Add‑on Store.  
2. Установите/обновите аддон и откройте его **Web UI**.  
3. Заполните секции: **Basics**, **Signal Strength**, **Bias (1h)**, **Setup (15m)**, **Trigger (5m)**, **Anti‑Noise**, **Exits & Costs** → **Save & Apply**.  
4. Статус смотрите вверху UI и по `/health`.

> **Миграция:** если видите предупреждения Supervisor «Option 'xxx' does not exist in the schema» — это остатки старых ключей в вашем конфиге аддона. Можно:
> - зайти в **Add‑on → Configuration** и удалить лишние строки (например `tp_levels_pct`),  
> - или нажать **Reset to defaults** и вернуть `telegram_token`/`telegram_chat_id`.  
> На работу аддона это не влияет; пер‑TF значения хранятся в `user_config.json` (UI‑only).

---

## Конфигурация аддона (минимум)
```json
{
  "telegram_token": "123:ABC",
  "telegram_chat_id": "123456789",
  "symbols_quote": "USDT",
  "top_n_by_volume": 120,
  "min_vol_24h_usd": 5000000,
  "cooldown_minutes": 20,
  "timezone": "Asia/Seoul",
  "use_level1_spread": false,
  "min_confirms": 3,

  "ema_fast": 20,
  "ema_mid": 50,
  "ema_slow": 200,
  "rsi_length": 14,
  "macd_fast": 12,
  "macd_slow": 26,
  "macd_signal": 9,

  "rvol15m_min": 1.6,
  "bias_rsi_min": 50,
  "bias_need_ema_order": true,
  "bias_allow_price_above_ema200_15m": true,
  "breakout_lookback_bars": 3,
  "macd_hist_rising_bars_min": 1,
  "macd_cross_up_allowed": true,

  "breakout_body_max_atr_mult": 1.8,
  "ema200_5m_min_distance_pct": 0.2,

  "taker_fee_bps": 10,
  "roundtrip_extra_buffer_bps": 5,
  "min_net_profit_bps": 0,

  "bias_ema_order_mode": "fast_over_mid",
  "bias_macd_condition": "hist_rising"
}
```
> `tp_levels_pct` теперь не валидируется схемой (0.2.5). Если всё‑таки хотите хранить в конфиге — добавляйте как **строку**: `"0.007, 0.012, 0.020"`.

---

## API/Служебные эндпоинты
- `GET /api/options` — текущие опции (включая UI‑only).  
- `POST /api/options` — сохранить изменения из UI.  
- `GET /api/set_min?val=N` — быстро задать минимальные подтверждения (3/4/5).  
- `GET /api/ping` — ping.  
- `GET /health` — статус: `ok`, `tracked_symbols`, `signals_sent`, `min_confirms`.

---

## Траблшутинг
- **IndentationError / компиляция** — проверьте отступы и табы/пробелы; все `.py` валидированы `py_compile`.  
- **Unknown error, see supervisor** при апдейте — обычно типы в конфиге не совпали со схемой. В 0.2.5 это решено для `tp_levels_pct`; если что — `Reset to defaults` и вернуть токены.  
- **Ворнинги Supervisor** об отсутствующих ключах в схеме — косметика, см. раздел «Миграция».

---

## Лицензия
MIT
