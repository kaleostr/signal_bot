#!/usr/bin/with-contenv bashio
set -euo pipefail
bashio::log.info "Starting Binance Spot Signals add-on…"

# Optional .env
if [ -f /addon_configs/binance_spot_signals_ws/.env ]; then
  set -a; . /addon_configs/binance_spot_signals_ws/.env; set +a
elif [ -f /data/.env ]; then
  set -a; . /data/.env; set +a
fi

CFG="/data/options.json"
export PYTHONPATH=/opt/app
bashio::log.info "Launching bot with /opt/venv/bin/python -m src.app"
exec /opt/venv/bin/python -m src.app --config "$CFG"
