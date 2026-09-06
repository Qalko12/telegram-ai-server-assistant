# Telegram AI Server & Coding Assistant

Production-ready Telegram-бот на Python 3.12 + aiogram 3.x + Claude API (tool calling), который управляет VPS через обычный человеческий язык: диагностика Linux/Docker, работа с файлами и логами, мониторинг с алертами, а также самостоятельное создание, редактирование, тестирование и деплой проектов прямо на сервере.

> Проект в разработке. Полное техническое задание — [`Текстовый документ.txt`](./Текстовый документ.txt), план реализации — [`docs/PLAN.md`](./docs/PLAN.md).

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

Разработка идёт поэтапно (15 фаз, от bootstrap до полной упаковки) — подробности в [плане](./docs/PLAN.md).

**Готово:**
- Фаза 0 (bootstrap) — конфигурация из `.env`, схема БД (8 таблиц) на SQLAlchemy + Alembic-миграции, Telegram-бот на aiogram с проверкой доступа по `ALLOWED_TELEGRAM_IDS`.
- Фаза 1 (security-скелет) — уровни действий (SAFE/MODERATE/CRITICAL), deny-list на деструктивные команды, проверка `ALLOWED_PATHS` с защитой от path traversal, одноразовые confirmation-кнопки с TTL и защитой от гонки, audit log каждого решения.
- Фаза 2 (AI-ядро) — подключён Claude API с tool calling, реестр инструментов на Pydantic-схемах, agent loop (лимит итераций, автоматическая защита от prompt injection через `<untrusted_tool_output>`), кратковременная память диалога в БД. MODERATE/CRITICAL-инструменты внутри диалога с ИИ пока не подключены к подтверждениям — это Фаза 3b.
- Фаза 3a (диагностика сервера) — `CommandExecutor` (безопасный subprocess с таймаутом и защитой от переполнения памяти при большом выводе), 16 SAFE-инструментов: системная информация, CPU/RAM/диск/процессы/сеть, статус и логи systemd-сервисов, системные логи и поиск по ним, безопасное чтение файлов и директорий (в пределах `ALLOWED_PATHS`), и `full_server_diagnostic` — по запросу «проверь сервер» ИИ сам проводит полную диагностику без уточняющих вопросов.

- Фаза 3b (Docker и управление сервисами) — agent loop теперь умеет ставить диалог на паузу: при вызове MODERATE/CRITICAL-инструмента бот шлёт inline-кнопки подтверждения, а после ответа пользователя возобновляет диалог с Claude с результатом (выполнено/отклонено). Добавлены `start/stop/restart_service`, `docker_ps/stats/logs/inspect` (SAFE), `docker_start/stop/restart` (MODERATE), `docker_exec` (CRITICAL, плюс deny-list на команду внутри контейнера). Итого 27 инструментов.

- Фаза 3c (файлы + execute) — `write_file`/`delete_file` с автоматическим бэкапом перед изменением (`write_file` умеет опциональную validate-команду с авто-откатом при провале), `create_directory`, `execute_command` (MODERATE, без shell) и `execute_shell` (CRITICAL, для пайпов/редиректов) — оба всегда проходят через deny-list, даже после подтверждения. Итого 32 инструмента.

Vision/OCR и работа с документами — следующий этап.

### Установка и запуск (текущий этап)

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # Linux/macOS

pip install -r requirements.txt

cp .env.example .env            # заполнить TELEGRAM_BOT_TOKEN, ANTHROPIC_API_KEY, ALLOWED_TELEGRAM_IDS

alembic upgrade head            # создать БД
python main.py                  # запустить бота
```

### Тесты

```bash
pip install -r requirements-dev.txt
pytest
```

## Безопасность

Бот работает с root-доступом на управляемом VPS. Единственный барьер — внутренний Security Layer (уровни действий, обязательные подтверждения для опасных операций, deny-list, backup/rollback). Никакие секреты не хранятся в коде — только в `.env` (см. `.env.example`, появится по мере разработки).
