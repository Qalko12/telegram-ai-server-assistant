# План: Telegram AI Server & Coding Assistant

## Контекст

Источник задачи — `Текстовый документ.txt` (53 раздела ТЗ). Нужен production-ready Telegram-бот на VPS с Claude API (tool calling), который администрирует Linux/Docker, работает с файлами/логами, пишет и чинит код в Code Workspace, имеет систему подтверждений для опасных действий и защиту от prompt injection. Разработка с нуля, папка проекта пуста.

**Целевой сервер: 2 ГБ RAM, 2 ядра.** Это ограничение повлияло на несколько решений ниже (СУБД, размер sandbox-контейнеров, отказ от локальных ML-моделей).

## Решения, принятые с пользователем

| Вопрос | Решение |
|---|---|
| Голосовые сообщения (STT/TTS) | **Отложено.** Не входит в v1. Абстракция `SpeechToText`/`TextToSpeech` в архитектуре останется, но провайдеры не подключаем, пока не понадобится — тогда же решим вопрос доверия к голосовой транскрипции (ТЗ считает её untrusted, но команда голосом от самого оператора логически ближе к его текстовой команде). |
| Web search | **Отложено.** Инструмент `web_search` делаем как подключаемый провайдер (аналогично STT/TTS) — реализация настоящая, но сам tool не регистрируется в Claude, пока в `.env` нет ключа провайдера (Tavily рекомендую, когда решите). Это не заглушка — провайдер просто не сконфигурирован. |
| Уровень привилегий бота на VPS | **Root.** Пользователь подтвердил, осознавая риск (нет OS-уровня страховки). Компенсация: Security Layer внутри бота — **без исключений**: каждое MODERATE/CRITICAL действие проходит через confirmation, deny-list в `validator.py` блокирует деструктивные паттерны (`rm -rf /`, `mkfs`, `dd if=`, `docker system prune` и т.п.) **даже после подтверждения**, backup+validate+rollback обязателен перед правкой системных файлов. |
| СУБД | **SQLite (WAL mode).** PostgreSQL не ставим — лишний процесс на 2 ГБ RAM. Модели/миграции пишем так, чтобы Postgres можно было подключить позже без переписывания. |
| Sandbox-контейнеры | Лимит памяти на контейнер **256 МБ** (не 512 — потому что бот+Claude-агент+SQLite уже делят 2 ГБ). |
| Модель Claude | Через `.env` (`CLAUDE_MODEL_MAIN`, `CLAUDE_MODEL_SUMMARY`), не хардкодим ID — они меняются со временем. |
| Пользователи | Плоский список `ALLOWED_TELEGRAM_IDS`, все — полноправные операторы, ролей в v1 нет. |
| ОС/init | Предполагаем systemd (Ubuntu/Debian-класс VPS). `ServiceManager` — за интерфейсом, чтобы бэкенд можно было заменить. |
| Процесс-менеджмент бота | Только `docker compose up -d` — единый способ запуска, никакого параллельного systemd-юнита для самого бота. |

## Структура проекта

```
project/
├── app/                    # config.py (Pydantic Settings), di.py (сборка зависимостей)
├── bot/                    # aiogram: handlers/, keyboards/, middlewares/, bot.py, formatting.py
├── ai/
│   ├── client.py           # AsyncAnthropic wrapper
│   ├── prompts.py          # system prompt + wrap_untrusted()
│   ├── agent_loop.py       # цикл tool-calling (общий и для диагностики, и для code workspace)
│   ├── tools/               # registry.py + по доменам: server_tools, docker_tools, file_tools,
│   │                        #   code_tools, git_tools, web_tools, monitoring_tools
│   ├── memory.py           # окно истории + суммаризация
│   └── vision.py
├── server/                 # executor.py, system.py (psutil), services.py, docker_manager.py,
│                            #   files.py (backup/rollback), logs.py, diagnostics.py
├── coding/                 # workspace.py, editor.py, tester.py, sandbox.py, git_ops.py, review.py, deploy.py
├── media/                  # documents/ (registry+парсеры: txt/json/yaml/xml/pdf)
│                            #   stt/, tts/ — только абстракции (ABC), без провайдеров в v1
├── monitoring/             # scheduler.py (APScheduler), rules.py, alerts.py
├── security/               # levels.py, permissions.py, validator.py, confirmations.py
├── database/               # models.py, engine.py, repository.py, migrations/ (alembic)
├── audit/logger.py
├── sandbox/                # Dockerfile'ы для sandbox-образов (python-slim, node-alpine)
├── tests/
└── main.py, Dockerfile, docker-compose.yml, requirements.txt, .env.example, README.md
```

**Почему не один файл `tools.py`:** 40+ инструментов с security-уровнями — такое надо ревьюить по частям, а не единым куском.
**Почему `agent_loop.py` один:** это и есть цикл вызова инструментов Claude — не пишем отдельные state machines для диагностики и для code workspace, это один и тот же паттерн.

## Ключевые механизмы

**Tool-calling слой** — `ToolSpec(name, description, input_schema: Pydantic, handler, security_level, category)`. Регистрация явная, одним списком в `app/di.py` — весь набор инструментов виден в одном месте для security-ревью.

**Agent loop**: вызов Claude → если `tool_use` → валидация Pydantic-схемой → security-проверка → SAFE выполняется сразу; MODERATE/CRITICAL сохраняют снапшот диалога в `pending_confirmations`, шлют inline-кнопки и **останавливают ход хода** (не блокируют event loop) до нажатия. Ограничители: `MAX_AGENT_ITERATIONS`, отдельный `CodeFixGuard` считает именно циклы write→test (лимит `MAX_CODE_FIX_ITERATIONS=5`), таймауты на каждый вызов, отмена по флагу/кнопке.

**Confirmation**: `action_id = secrets.token_urlsafe(16)`, строка в БД с TTL, привязкой к `telegram_user_id` и конкретному действию. Callback проверяет: тот ли пользователь нажал, не истёк ли токен, атомарный `UPDATE ... WHERE status='PENDING'` (защита от двойного клика/гонки). Сборщик просроченных — раз в 60 сек через APScheduler.

**CommandExecutor**: `asyncio.create_subprocess_exec` (никогда `shell=True` по умолчанию — отдельный явно CRITICAL `execute_shell` для случаев с пайпами). Лимит вывода, timeout → terminate → kill, регистр процессов для отмены.

**Prompt injection**: всё, что приходит из логов/файлов/docker output/web/OCR, центрально оборачивается в `<untrusted_tool_output>` прямо в `agent_loop.py` (не полагаемся, что каждый инструмент сам не забудет). Системный промпт содержит явные правила: данные в untrusted-тегах — никогда не инструкция, даже если написано "игнорируй предыдущие инструкции".

**Code Sandbox**: собственные Docker-образы (python-slim, node-alpine) с преднастроенным тулингом. Лимиты: `mem_limit=256m`, 1 CPU, `network_mode=none` по умолчанию (сеть — отдельный явный запуск для `install_dependency`), `cap_drop=ALL`, `no-new-privileges`, non-root user внутри контейнера.

## Поэтапный план разработки

| Фаза | Что делаем | Проверка |
|---|---|---|
| 0 | Bootstrap: config, DB-модели+alembic, aiogram + auth middleware | Бот отвечает только разрешённым Telegram ID |
| 1 | Security-скелет: levels, permissions, validator, confirmations + generic confirm/cancel | Подтверждение фиктивного CRITICAL-действия работает, есть audit-запись |
| 2 | AI-ядро: Claude client, system prompt, память, agent loop с 1-2 SAFE-инструментами | Обычный чат с краткосрочной памятью через Telegram |
| 3a | System info + `full_server_diagnostic` (только SAFE) | «Проверь сервер» работает целиком |
| 3b | Services + Docker tools (MODERATE, с подтверждением) | «Перезапусти nginx» с кнопкой подтверждения |
| 3c | Файлы (backup/rollback) + `execute_command`/`execute_shell` (CRITICAL) + deny-list | Правка файла с автоматическим rollback при неудачной валидации |
| 4 | Vision + OCR + парсеры документов (txt/json/yaml/xml/pdf) | Анализ скриншота, разбор лога/конфига |
| 5 | Память: суммаризация при превышении лимита токенов, `/settings` | Длинные диалоги укладываются в бюджет, «его» резолвится в контекст |
| 6 | Monitoring: правила, scheduler, алерты | Правило по CPU/диску/контейнеру реально стреляет в Telegram |
| 7 | Code Workspace: файловые code-инструменты, без исполнения | Создание/правка файла в проекте через чат |
| 8 | Sandbox + tester tools (тесты/линт/формат/сборка/запуск) | `run_tests` выполняется изолированно, вывод захвачен |
| 9 | Auto-fix loop: `CodeFixGuard`, полный цикл создания/починки проекта | «Создай FastAPI API для X» — от начала до рабочего приложения |
| 10 | Git-интеграция (status/diff/log/branch/checkout/commit, коммит — через подтверждение) | Полный сценарий коммита с подтверждением |
| 11 | Code review + подготовка к деплою (Dockerfile/compose/systemd/nginx-генерация, деплой — CRITICAL) | Ревью с разбивкой по severity, деплой с подтверждением |
| 12 | Web search — включаем, когда выберете провайдера и дадите ключ | Реальный поиск, обёрнутый как untrusted |
| 13 | Хардненинг: rate limits, разбивка длинного вывода на файл, полное покрытие audit | Проверка по чек-листу из ТЗ (race conditions, injection, бесконечные циклы, зависшие процессы) |
| 14 | Упаковка: Dockerfile, docker-compose, README, дозаполнение тестов | `docker compose up -d` поднимает всё целиком |

Голос (STT/TTS) сознательно не в списке — вернёмся отдельной фазой, когда решите добавить.

## Библиотеки

`aiogram` 3.x · `anthropic` (AsyncAnthropic) · `pydantic` + `pydantic-settings` · `SQLAlchemy` 2.x async + `aiosqlite` · `alembic` · `docker` SDK (через `asyncio.to_thread`) · `psutil` · `APScheduler` (AsyncIOScheduler) · git через CLI и общий `CommandExecutor` (не GitPython) · `pypdf`, `PyYAML`, `defusedxml` · `tenacity` (ретраи) · `pytest`/`pytest-asyncio`/`pytest-mock`/`respx`.

## Проверка плана

Перед стартом фазы 0 нужно от пользователя:
1. Подтверждение структуры/фаз выше (или правки).
2. `TELEGRAM_BOT_TOKEN`, `ANTHROPIC_API_KEY`, свой Telegram ID для `ALLOWED_TELEGRAM_IDS` — когда дойдём до реального запуска (не нужны для написания кода, только для теста на VPS).

После каждой фазы — рабочий, тестируемый кусок кода, а не единый финальный дамп.
