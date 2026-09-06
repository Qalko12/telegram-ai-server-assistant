# Telegram AI Server & Coding Assistant

Production-ready Telegram-бот на Python 3.12 + aiogram 3.x + Claude API (tool calling), который управляет VPS через обычный человеческий язык: диагностика Linux/Docker, работа с файлами и логами, мониторинг с алертами, а также самостоятельное создание, редактирование, тестирование и деплой проектов прямо на сервере.

> Проект в разработке. Полное ТЗ — [`Текстовый документ.txt`](./Текстовый документ.txt), план реализации — [`tmp/plans/telegram-ai-assistant-plan.md`](./tmp/plans/telegram-ai-assistant-plan.md).

## Возможности

- **Обычный чат** вместо команд: «проверь сервер», «почему backend падает?», «напиши мне API на FastAPI»
- **Server management**: CPU/RAM/диск/процессы/сеть, systemd-сервисы, логи, полная диагностика одной командой
- **Docker**: контейнеры, статистика, логи, restart/stop/start
- **Code Workspace**: AI пишет, тестирует и чинит код прямо на VPS, с auto-fix циклом и лимитом итераций
- **Git-интеграция**: status/diff/log/branch, коммит — только через подтверждение
- **Vision + OCR**: анализ скриншотов, терминалов, логов на фото
- **Мониторинг и алерты**: пользовательские правила («если CPU > 90% — сообщи»)
- **Security Layer**: три уровня действий (SAFE / MODERATE / CRITICAL), одноразовые confirmation-кнопки с TTL, deny-list на деструктивные команды, backup+rollback перед правкой системных файлов
- **Защита от prompt injection**: все внешние данные (логи, файлы, docker output, web-результаты) — недоверенный контент, не может менять поведение AI
- **Audit log**: каждое действие бота записывается

## Технологии

Python 3.12+ · aiogram 3.x · Claude API (Anthropic SDK) · asyncio · Docker · SQLite (SQLAlchemy async) · Pydantic · APScheduler

## Статус разработки

Разработка идёт поэтапно (15 фаз, от bootstrap до полной упаковки) — подробности в [плане](./tmp/plans/telegram-ai-assistant-plan.md). Инструкции по установке и запуску появятся здесь по мере готовности первых фаз.

## Безопасность

Бот работает с root-доступом на управляемом VPS. Единственный барьер — внутренний Security Layer (уровни действий, обязательные подтверждения для опасных операций, deny-list, backup/rollback). Никакие секреты не хранятся в коде — только в `.env` (см. `.env.example`, появится по мере разработки).
