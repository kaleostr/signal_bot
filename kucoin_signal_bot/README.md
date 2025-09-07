# KuCoin Spot Signal Bot — Home Assistant Add-on

**Версия:** 0.2.8  
Тёмный Web UI • Пер‑таймфрейм настройки (1h / 15m / 5m) • Логика Bias → Setup → Trigger • Анти‑шум • Подсказки при наведении по всему UI

---

## Что нового

### 0.2.8
- Полностью обновлённый README и мелкие правки текста в подсказках.

### 0.2.7
- **Подсказки по всему UI**: Basics, Signal Strength, Bias/Setup/Trigger, Anti‑Noise, Exits & Costs, кнопки управления.

### 0.2.6
- Подсказки на ключевых полях индикаторов (EMA/RSI/MACD, RVOL, анти‑шум, комиссии) + чекбокс **Require EMA order**.

### 0.2.5
- Схема конфига стала толерантнее: убрана строгая валидация `tp_levels_pct` (чтобы апдейты не падали из‑за строк/списков).  
  Если предупреждение в логе мешает — удалите ключ `tp_levels_pct` из конфигурации аддона (см. ниже).

### 0.2.4
- Расширены `schema/options` для всех часто встречающихся «легаси»-ключей, чтобы Supervisor не ругался на них.

### 0.2.3
- Минимизирована схема, добавлен README, миграционные примечания.

### 0.2.2
- Веб‑UI: отдельные секции **Bias 1h / Setup 15m / Trigger 5m / Anti‑Noise / Exits & Costs**.  
- Пер‑TF параметры стали **UI‑only** (не захламляют `options.json`).  
- Переписаны правила и индикаторы с фоллбеком на старые ключи.

---

## Возможности

- **Пер‑TF параметры (UI‑only)**  
  - **Bias (1h):** `ema_fast_1h`, `ema_mid_1h`, `ema_slow_1h`, `rsi_len_1h`, `rsi_min_1h`, `macd_fast_1h`, `macd_slow_1h`, `macd_signal_1h`, а также:  
    `bias_need_ema_order` (вкл/выкл), `bias_ema_order_mode` (`fast_over_mid` | `mid_over_slow`), `bias_macd_condition` (`hist_rising` | `macd_ge_0` | `off`).
  - **Setup (15m):** EMA‑трио, RSI len/min, MACD 12/26/9, `rvol15m_min` (1.6).
  - **Trigger (5m):** EMA 9/21/50, RSI9 over 55, MACD 8/21/5, VWAP↑ & price>VWAP.
- **Анти‑шум:** лимит тела пробоя `ATR×mult`, минимальная дистанция до EMA200 (5m).  
- **Выходы/издержки:** тейки в десятичной форме (`0.007, 0.012, 0.020`), `taker_fee_bps`, `roundtrip_extra_buffer_bps`, `min_net_profit_bps`.  
- **Учет спреда L1:** опция **Use Level1 spread adjust** корректирует вход/тейки и фильтрует низкую чистую прибыль.  
- **Фоллбек:** если пер‑TF значение не задано — берутся старые общие ключи (`ema_fast`, `ema_mid`, `ema_slow`, `rsi_length`, `macd_*`).

### Рекомендуемые дефолты
- **1h:** EMA 20/50/200, RSI14 min 50, MACD 12/26/9  
- **15m:** EMA 20/50/200, RSI14 min 50, MACD 12/26/9, RVOL 1.6  
- **5m:** EMA 9/21/50, RSI9 over 55, MACD 8/21/5

---

## Установка / Обновление

1. Добавьте репозиторий кастомных аддонов в Home Assistant **Add‑on Store**.  
2. Установите/обновите аддон, откройте **Web UI**.  
3. Заполните секции: **Basics**, **Signal Strength**, **Bias (1h)**, **Setup (15m)**, **Trigger (5m)**, **Anti‑Noise**, **Exits & Costs** → **Save & Apply**.  
4. Статус виден вверху страницы и по `/health`.

> **Миграция и предупреждения Supervisor**  
> - Сообщение «Option 'tp_levels_pct' does not exist in the schema» означает, что в конфиге аддона остался старый ключ. Это **не критично**.  
> - Чтобы убрать предупреждение: Add‑on → **Configuration** → удалить строку `tp_levels_pct` (или **Reset to defaults**, затем вернуть токены Telegram).  
> - Пер‑TF параметры хранятся в `user_config.json` (UI‑only), а не в `options.json`.

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

> `tp_levels_pct` можно хранить в UI (рекомендуется). Если хотите держать в конфиге — используйте **строку**: `"0.007, 0.012, 0.020"`.

---

## Эндпоинты

- `GET /api/options` — получить текущие опции (включая UI‑only).  
- `POST /api/options` — сохранить из UI.  
- `GET /api/set_min?val=N` — быстрый выбор минимума подтверждений (3/4/5).  
- `GET /api/ping` — ping.  
- `GET /health` — статус: `ok`, `tracked_symbols`, `signals_sent`, `min_confirms`.

---

## Траблшутинг

- **IndentationError / компиляция** — проверьте отступы; все `.py` проверены `py_compile`.  
- **Unknown error, see supervisor** — чаще всего конфликт типов в конфиге; используйте Reset или приведите ключи к типам из схемы.  
- **Ворнинги Supervisor** об «Option ... not in the schema» — косметика (см. «Миграция»).

---

## Лицензия

MIT
