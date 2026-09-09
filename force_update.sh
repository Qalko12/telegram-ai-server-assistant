#!/bin/bash
set -euo pipefail

APP_DIR="/opt/telegram-ai-server-assistant"

echo "=== Принудительное обновление ==="

# Останавливаем бота
cd "$APP_DIR"
docker compose down

# Удаляем старые файлы (кроме .env и data)
echo "Удаляю старые файлы..."
find "$APP_DIR" -mindepth 1 -maxdepth 1 ! -name '.env' ! -name 'data' ! -name 'docker-compose.yml' -exec rm -rf {} +

# Распаковываем новую версию
echo "Распаковываю..."
tar -xzf /root/telegram-ai-assistant-v3.tar.gz -C "$APP_DIR"

# Проверяем, что file_send_tools.py появился
if [ -f "$APP_DIR/ai/tools/file_send_tools.py" ]; then
  echo "✅ file_send_tools.py на месте"
else
  echo "❌ file_send_tools.py НЕ НАЙДЕН!"
  exit 1
fi

# Пересобираем и запускаем
echo "Пересобираю и запускаю..."
docker compose up -d --build

sleep 10
docker compose ps
echo ""
docker compose logs --tail=10 assistant

echo ""
echo "=== Проверка инструмента ==="
docker exec telegram-ai-assistant python -c "
import sys
sys.path.insert(0, '/app')
from app.di import build_tool_registry
r = build_tool_registry()
tools = [t['name'] for t in r.to_anthropic_tools()]
print(f'Total: {len(tools)}')
print(f'send_file_to_chat: {\"send_file_to_chat\" in tools}')
"
