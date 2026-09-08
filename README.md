# Telegram AI Server & Coding Assistant

Production-ready Telegram-бот на Python 3.12 + aiogram 3.x + Claude API (tool calling), который управляет VPS обычным человеческим языком: диагностика Linux/Docker, systemd, файлы и логи, мониторинг с алертами, а также самостоятельное создание, редактирование, тестирование, ревью и деплой проектов прямо на сервере.

> Полное техническое задание — [`Текстовый документ.txt`](./Текстовый документ.txt), архитектурный план — [`docs/PLAN.md`](./docs/PLAN.md).

## Возможности

- **Обычный чат** вместо команд: «проверь сервер», «почему backend падает?», «создай FastAPI API для X»
- **Server management**: CPU/RAM/диск/процессы/сеть, systemd-сервисы, логи, полная диагностика одним «проверь сервер»
- **Docker**: контейнеры, статистика, логи, inspect, start/stop/restart, exec
- **Code Workspace** (`/opt/ai-workspace`): AI создаёт проекты, пишет и правит код, ищет по коду, гоняет тесты/линт/форматтер/сборку в изолированном Docker-sandbox
- **Auto-fix**: цикл «правка → тесты → анализ → правка» с жёстким лимитом (`MAX_CODE_FIX_ITERATIONS`)
- **Git**: status/diff/log/branch/checkout; commit — только через подтверждение, в основной ветке — с предупреждением
- **Code review**: снимок проекта → разбор по severity (🔴 Critical / 🟠 High / 🟡 Medium / 🟢 Low)
- **Deployment**: генерация Dockerfile/docker-compose/systemd-unit/nginx-конфига, сборка образа, запуск контейнера на 127.0.0.1, healthcheck — всё через CRITICAL-подтверждение
- **Vision + OCR**: анализ скриншотов и фото терминала (Claude Vision), извлечённый текст используется для диагностики
- **Документы**: TXT/LOG/JSON/YAML/XML/PDF — парсятся и анализируются вместе с подписью
- **Память диалога**: история в БД, автоматическая суммаризация при превышении токен-бюджета, «покажи его логи» корректно резолвит «его»
- **Мониторинг и алерты**: правила «если CPU > 90% пять минут — сообщи», «если контейнер backend упадёт — сообщи», с отслеживанием длительности и cooldown
- **Web search**: подключаемый провайдер (Tavily) — регистрируется только при заданном ключе
- **Security Layer**: SAFE/MODERATE/CRITICAL, одноразовые confirmation-кнопки с TTL и защитой от гонки, deny-list деструктивных команд (даже после подтверждения), backup+validate+rollback при правке файлов, path-traversal защита
- **Prompt injection protection**: весь вывод инструментов (логи, файлы, docker, web) оборачивается в `<untrusted_tool_output>` — данные никогда не становятся инструкциями
- **Rate limits**: скользящие окна на сообщения, прогоны агента, команды, sandbox и web search
- **Audit log**: каждое действие (кто, что, аргументы, результат, время, успех) — в БД
- **Длинный вывод**: режется на части, очень большой — дублируется файлом

## Требования

- VPS с Linux (Ubuntu/Debian), systemd, Docker и Docker Compose plugin
- 2 ГБ RAM / 2 ядра — минимум (проверено архитектурно: SQLite WAL, лимиты sandbox 256 МБ)
- Telegram-бот токен и Anthropic API key (см. ниже)
- Опционально: Tavily API key для web search

## Быстрый старт

### 1. Установить Docker (если ещё нет)

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER   # и перелогиниться
```

### 2. Создать Telegram-бота

1. Напишите [@BotFather](https://t.me/BotFather) → `/newbot` → придумайте имя и username.
2. Скопируйте выданный токен — это `TELEGRAM_BOT_TOKEN`.

### 3. Получить Claude API key

1. Зайдите на [console.anthropic.com](https://console.anthropic.com/) → **Settings → API Keys** → **Create Key**.
2. Скопируйте ключ — это `ANTHROPIC_API_KEY`. (Нужен оплаченный баланс или триал.)

### 4. Узнать свой Telegram ID

Напишите [@userinfobot](https://t.me/userinfobot) — он ответит вашим числовым ID. Это значение для `ALLOWED_TELEGRAM_IDS` (через запятую, если операторов несколько).

### 5. Настроить .env

```bash
git clone https://github.com/Qalko12/telegram-ai-server-assistant.git
cd telegram-ai-server-assistant
cp .env.example .env
nano .env   # заполнить TELEGRAM_BOT_TOKEN, ANTHROPIC_API_KEY, ALLOWED_TELEGRAM_IDS
```

### 6. Собрать sandbox-образы

Это образы, в которых AI запускает тесты/код проектов (изолированно от VPS):

```bash
docker build -f sandbox/python.Dockerfile -t ai-sandbox-python:latest sandbox/
docker build -f sandbox/node.Dockerfile -t ai-sandbox-node:latest sandbox/
```

### 7. Создать каталоги на хосте

```bash
sudo mkdir -p /opt/ai-workspace /var/backups/ai-assistant
```

### 8. Запустить

```bash
docker compose up -d --build
docker compose logs -f          # первые логи
```

Миграции БД применяются автоматически при старте (entrypoint). Напишите боту «проверь сервер» — он проведёт полную диагностику.

## Остановка / обновление / бэкап

```bash
docker compose stop             # остановить
docker compose down             # остановить и удалить контейнер (данные в ./data останутся)

git pull                        # обновить код
docker compose up -d --build    # пересобрать и перезапустить

cp data/bot.db data/bot.db.bak  # бэкап БД (история, правила, audit, подтверждения)
tar czf backups-$(date +%F).tar.gz /var/backups/ai-assistant /opt/ai-workspace   # бэкап workspace и файловых бэкапов
```

## Просмотр логов

```bash
docker compose logs -f assistant          # логи бота
sqlite3 data/bot.db "SELECT timestamp, tool_name, success FROM audit_logs ORDER BY id DESC LIMIT 20;"  # audit
```

## Команды бота

Команды не обязательны — основное взаимодействие обычный чат. Доступны:
`/start` `/help` `/status` `/server` `/docker` `/logs` `/processes` `/disk` `/services` `/projects` `/coding` `/settings` `/clear`

`/settings` — runtime-настройки (хранятся в БД, переживают перезапуск):

```
/settings                                  — список
/settings history_keep_recent 15           — изменить
/settings memory_summarization_enabled false
/settings voice_response_mode text
/settings history_keep_recent reset        — сбросить в дефолт
/clear                                     — очистить память диалога
```

## Голосовые функции (STT/TTS)

В v1 голосовые сообщения **не подключены** (решение в [PLAN.md](./docs/PLAN.md)): в `media/speech.py` готовы абстракции `SpeechToText` / `TextToSpeech` и `VoicePipeline` с политикой режимов (text/voice/auto). Добавление провайдера (Whisper API, Yandex SpeechKit и т.д.) — один класс + фабрика, без правок ядра. Настройки `VOICE_RESPONSES_ENABLED` / `VOICE_RESPONSE_MODE` уже поддержаны. Транскрипция голоса будет обрабатываться как недоверенный ввод (как документы и OCR).

## Web search

Инструмент `web_search` реализован поверх [Tavily API](https://tavily.com) (есть бесплатный тариф). Пока `TAVILY_API_KEY` пуст — инструмент просто не регистрируется у Claude. Как только ключ задан — поиск включается автоматически; результаты помечаются как недоверенные данные.

## Полный список AI tools

### Server (SAFE — выполняются сразу)

| Tool | Назначение |
|---|---|
| `get_uptime` | время работы сервера |
| `get_cpu_usage` | загрузка CPU |
| `get_system_info` | хост, ОС, ядро |
| `get_ram_usage` | память |
| `get_disk_usage` / `get_disk_details` | диск по точкам монтирования |
| `get_processes` | топ процессов по CPU/RAM |
| `get_network_info` | интерфейсы и адреса |
| `get_service_status` / `get_service_logs` | systemd-сервис и его journalctl |
| `get_system_logs` / `search_logs` | системные логи и поиск по ним |
| `list_directory` / `find_file` / `read_file` | чтение ФС в пределах `ALLOWED_PATHS` |
| `full_server_diagnostic` | полная диагностика: «проверь сервер» |
| `docker_ps` / `docker_stats` / `docker_logs` / `docker_inspect` | чтение состояния Docker |
| `list_monitoring_rules` | правила мониторинга |
| `list_projects` / `list_project_files` / `read_code_file` / `search_code` / `find_code_references` | чтение Code Workspace |
| `git_status` / `git_diff` / `git_log` | чтение git |
| `review_project` | материал для code review |
| `run_tests` / `run_linter` / `run_formatter` / `run_build` | прогон в Docker-sandbox (изолированно) |
| `web_search` | поиск в интернете (если настроен Tavily) |

### MODERATE — требуют confirmation-кнопку

`start_service` `stop_service` `restart_service` · `docker_start` `docker_stop` `docker_restart` · `write_file` (с бэкапом и валидацией) `delete_file` `create_directory` · `execute_command` · `create_monitoring_rule` `delete_monitoring_rule` `set_monitoring_rule_enabled` · `delete_code_file` · `install_dependency` `run_project` · `git_init` `git_create_branch` `git_checkout` `git_commit` · `prepare_deployment`

### CRITICAL — всегда явное подтверждение + deny-list

`execute_shell` · `docker_exec` · `deploy_project` (сборка образа + запуск контейнера + healthcheck)

## Security Layer — как это работает

1. **Авторизация**: бот отвечает только ID из `ALLOWED_TELEGRAM_IDS`; остальным — «⛔ Доступ запрещён», никакие инструменты не вызываются.
2. **Уровни действий**: SAFE — сразу; MODERATE/CRITICAL — ход агента ставится на паузу, в чат приходит карточка «⚠️ ТРЕБУЕТСЯ ПОДТВЕРЖДЕНИЕ» с кнопками. Подтверждение одноразовое (TTL 5 минут), привязано к user ID и конкретному действию с аргументами; атомарный UPDATE защищает от двойного клика.
3. **Deny-list** (`security/validator.py`): `rm -rf /`, `mkfs`, `dd if=`, `docker system prune`, fork bomb, перезапись блочных устройств — блокируются **даже после подтверждения**.
4. **Файлы**: `write_file`/`delete_file` делают бэкап в `BACKUP_DIR` до изменения; с `validate_command` (например `nginx -t`) при провале проверки — автоматический rollback. Все пути проверяются на принадлежность `ALLOWED_PATHS` + блок `~/.ssh`, `/etc/shadow`; code-инструменты дополнительно заперты внутри Code Workspace (path-escape блокируется).
5. **Команды**: только `create_subprocess_exec` без shell; `execute_shell` — отдельный CRITICAL-инструмент; у всех — таймаут (terminate→kill), лимит вывода, логирование.
6. **Prompt injection**: вывод каждого инструмента оборачивается в `<untrusted_tool_output>` централизованно в agent loop; системный промпт запрещает treat'ить данные как инструкции. Содержимое документов/фото/веба — тоже данные.
7. **Rate limits**: скользящее окно на сообщения (20/мин), прогоны агента (10/мин), команды (30/мин), sandbox (10/5мин), web search (10/мин).
8. **Бесконечные циклы**: лимит итераций агента (`MAX_AGENT_ITERATIONS=30`) + `CodeFixGuard` (лимит циклов правка→упавшие тесты, по умолчанию 5).
9. **Audit**: каждое подтверждённое действие пишется в `audit_logs` (user, tool, аргументы, результат, время, успех/ошибка).

## Code Workspace — как это работает

- Корень: `CODE_WORKSPACE=/opt/ai-workspace`; каждый проект — поддиректория (`/opt/ai-workspace/my-api/`).
- «Создай Telegram-бота на Python» → `create_project` → AI пишет код (`write_code_file`/`edit_code_file`) → `run_tests` в sandbox → при ошибке анализирует и правит (auto-fix, лимит 5 циклов) → `git init`/commit через подтверждение → при желании `prepare_deployment` + `deploy_project` (CRITICAL) с healthcheck.
- Исполнение кода — **только** в sandbox-контейнере: `--network none` (кроме install/run), `--cap-drop ALL`, `no-new-privileges`, non-root user, лимиты 256 МБ / 1 CPU, принудительное удаление по таймауту.
- «Проверь /opt/mybot, почему он падает» → list files → search code → read files → логи → диагноз → правка (бэкап/ветка) → тесты → отчёт.

## Управление systemd из контейнера

`systemctl`/`journalctl` внутри контейнера работают против хоста через примонтированные сокеты (см. `docker-compose.yml`: `/run/systemd/private`, журналы). Ограничение: на некоторых дистрибутивах `systemctl` требует D-Bus — тогда добавьте в volumes:

```yaml
- /run/dbus/system_bus_socket:/run/dbus/system_bus_socket
```

Если управление сервисами критично и контейнерный вариант капризничает — запустите бота прямо на хосте (см. «Запуск без Docker» ниже): на поведение Security Layer это не влияет.

## Запуск без Docker (dev)

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt requirements-dev.txt
cp .env.example .env               # заполнить ключи
python -m alembic upgrade head
python main.py
```

## Тесты

```bash
pip install -r requirements-dev.txt
pytest                             # 271 тест: юнит + интеграционные (реальные git-репозитории, TCP-healthcheck)
```

## Добавление нового инструмента

1. Реализуйте handler в нужном модуле `ai/tools/*.py` (Pydantic-схема параметров обязательна).
2. Создайте `ToolSpec(name, description, input_model, handler, security_level)` — уровень выбирайте по [таблице ТЗ §12](./Текстовый%20документ.txt).
3. Зарегистрируйте в `app/di.py` (`build_tool_registry`).
4. Вывод инструмента автоматически станет untrusted-данными — специально оборачивать не нужно.
5. Добавьте тест по образцу `tests/test_tools_registry.py` / `tests/test_server_tools.py`.

## Добавление нового проекта (в смысле бота)

Проекты создаёт сам AI через `create_project` (или вы вручную: `mkdir /opt/ai-workspace/my-project`). Реестр в таблице `projects` синхронизируется автоматически при первой записи файла.

## Архитектура

```
Telegram → aiogram handlers → RateLimit/Auth middlewares
    → память (история + суммаризация) → AgentLoop ⇄ Claude (tool calling)
        → ToolRegistry (Pydantic-валидация) → Security Layer (уровень, deny-list, confirmation)
            → CommandExecutor / psutil / docker CLI / git CLI / Docker-sandbox
    → результат (wrap_untrusted) → Claude → ответ (чанки/файл) → Telegram
Фон: APScheduler (sweep подтверждений, мониторинг-правила → алерты)
БД: SQLite WAL (users, settings, history, summaries, rules, confirmations, audit, projects)
```

Модули: `bot/` (Telegram), `ai/` (Claude + tools), `server/` (Linux/Docker/файлы), `coding/` (workspace/sandbox/git/deploy/review), `media/` (документы), `monitoring/`, `security/`, `database/`, `audit/`.

## Лицензия

MIT — используйте на свой страх и риск: бот проектировался под root на вашем VPS с полным Security Layer, но ответственность за действия на сервере несёт оператор.
