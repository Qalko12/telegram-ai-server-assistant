#!/bin/sh
# Применяет миграции БД и запускает бота.
set -e

echo "Applying database migrations..."
python -m alembic upgrade head

echo "Starting Telegram AI assistant..."
exec python main.py
