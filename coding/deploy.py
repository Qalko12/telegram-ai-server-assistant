"""Подготовка проекта к деплою (ТЗ §35).

Генерирует артефакты развёртывания для проекта Code Workspace:
- Dockerfile (python/node по языку проекта);
- docker-compose.yml (приложение + healthcheck);
- .env.example (если ещё нет);
- systemd unit (альтернативный способ запуска без Docker);
- фрагмент nginx-конфига (reverse proxy на порт приложения).

Артефакты записываются в deploy/ внутри проекта. Сам деплой (сборка образа и
запуск контейнера на VPS) выполняется отдельным CRITICAL-инструментом и всегда
требует подтверждения оператора. Healthcheck — простой HTTP/TCP-опрос.
"""

import asyncio
import socket
from pathlib import Path

from coding.tester import detect_language
from coding.workspace import WorkspaceError
from server.executor import CommandExecutor

DEPLOY_DIR = "deploy"


class DeployArtifactError(WorkspaceError):
    pass


def _deploy_dir(project_path: Path) -> Path:
    path = project_path / DEPLOY_DIR
    path.mkdir(parents=True, exist_ok=True)
    return path


def _write_artifact(path: Path, content: str) -> str:
    path.write_text(content, encoding="utf-8")
    return path.name


def generate_dockerfile(project_path: Path, *, port: int = 8000) -> str:
    language = detect_language(project_path)
    if language == "node":
        content = f"""FROM node:20-alpine

WORKDIR /app
COPY package*.json ./
RUN npm ci --omit=dev || npm install --omit=dev

COPY . .

ENV NODE_ENV=production PORT={port}
EXPOSE {port}
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \\
  CMD wget -qO- http://127.0.0.1:{port}/health || exit 1

CMD ["npm", "start"]
"""
    else:
        content = f"""FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONUNBUFFERED=1
EXPOSE {port}
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \\
  CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:{port}/health', timeout=3)" || exit 1

CMD ["python", "app/main.py"]
"""
    return _write_artifact(_deploy_dir(project_path) / "Dockerfile", content)


def generate_compose(project_path: Path, *, project_name: str, port: int = 8000) -> str:
    content = f"""services:
  {project_name}:
    build:
      context: ..
      dockerfile: deploy/Dockerfile
    restart: unless-stopped
    ports:
      - "127.0.0.1:{port}:{port}"
    env_file:
      - ../.env
    healthcheck:
      test: ["CMD-SHELL", "python -c \\"import urllib.request;urllib.request.urlopen('http://127.0.0.1:{port}/health', timeout=3)\\" || wget -qO- http://127.0.0.1:{port}/health || exit 1"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 10s
"""
    return _write_artifact(_deploy_dir(project_path) / "docker-compose.yml", content)


def generate_systemd_unit(project_path: Path, *, project_name: str, port: int = 8000) -> str:
    content = f"""[Unit]
Description={project_name} (managed by AI assistant)
After=network.target

[Service]
Type=simple
WorkingDirectory={project_path.resolve()}
ExecStart=/usr/bin/python3 app/main.py
Environment=PORT={port}
Restart=on-failure
RestartSec=5
# Ограничение привилегий
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
ProtectHome=read-only

[Install]
WantedBy=multi-user.target
"""
    return _write_artifact(_deploy_dir(project_path) / f"{project_name}.service", content)


def generate_nginx_config(project_path: Path, *, project_name: str, port: int = 8000, server_name: str = "_") -> str:
    content = f"""# Фрагмент reverse-proxy для {project_name}.
# Включить: скопировать в /etc/nginx/sites-available/{project_name}.conf,
# сделать симлинк в sites-enabled, проверить `nginx -t`, перезапустить nginx.
server {{
    listen 80;
    server_name {server_name};

    location / {{
        proxy_pass http://127.0.0.1:{port};
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 60s;
    }}

    location /health {{
        proxy_pass http://127.0.0.1:{port}/health;
        access_log off;
    }}
}}
"""
    return _write_artifact(_deploy_dir(project_path) / f"{project_name}.nginx.conf", content)


def generate_env_example(project_path: Path, *, port: int = 8000) -> str | None:
    env_example = project_path / ".env.example"
    if env_example.exists():
        return None
    content = f"""# Скопируйте в .env и заполните реальными значениями.
PORT={port}
# DATABASE_URL=
# SECRET_KEY=
"""
    env_example.write_text(content, encoding="utf-8")
    return env_example.name


def prepare_all(project_path: Path, *, project_name: str, port: int = 8000) -> list[str]:
    """Генерирует полный комплект артефактов деплоя."""
    created = [
        generate_dockerfile(project_path, port=port),
        generate_compose(project_path, project_name=project_name, port=port),
        generate_systemd_unit(project_path, project_name=project_name, port=port),
        generate_nginx_config(project_path, project_name=project_name, port=port),
    ]
    env_name = generate_env_example(project_path, port=port)
    if env_name:
        created.append(env_name)
    return created


async def build_and_start_container(
    project_path: Path,
    *,
    project_name: str,
    port: int,
    executor: CommandExecutor | None = None,
) -> str:
    """Собирает образ и запускает контейнер. CRITICAL — вызывается только после подтверждения.

    Контейнер публикуется только на 127.0.0.1 (доступ снаружи — через nginx).
    """
    executor = executor or CommandExecutor(timeout=600, max_output_size=20000)
    deploy_dir = project_path / DEPLOY_DIR
    image_name = f"ai-deploy-{project_name}:latest"
    container_name = f"ai-{project_name}"

    build = await executor.run(
        "docker",
        ["build", "-f", str(deploy_dir / "Dockerfile"), "-t", image_name, str(project_path.resolve())],
    )
    if not build.success:
        raise DeployArtifactError(
            f"Сборка образа не удалась (exit={build.exit_code}):\n{(build.stderr or build.stdout)[-3000:]}"
        )

    # Снять старый контейнер, если он есть.
    await executor.run("docker", ["rm", "-f", container_name])

    run_result = await executor.run(
        "docker",
        [
            "run", "-d",
            "--name", container_name,
            "--restart", "unless-stopped",
            "--memory", "256m",
            "--cpus", "1.0",
            "-p", f"127.0.0.1:{port}:{port}",
            image_name,
        ],
    )
    if not run_result.success:
        raise DeployArtifactError(
            f"Запуск контейнера не удался (exit={run_result.exit_code}):\n{run_result.stderr or run_result.stdout}"
        )
    return f"Образ {image_name} собран, контейнер {container_name} запущен на 127.0.0.1:{port}."


async def healthcheck(port: int, *, retries: int = 6, delay: float = 5.0, path: str = "/health") -> tuple[bool, str]:
    """Ждёт старта приложения и опрашивает HTTP-эндпоинт (или TCP-порт как fallback)."""
    last_error = ""
    for attempt in range(retries):
        try:
            reader, writer = await asyncio.open_connection("127.0.0.1", port)
            writer.close()
            await writer.wait_closed()
        except OSError as exc:
            last_error = f"порт {port} недоступен: {exc}"
            await asyncio.sleep(delay)
            continue

        # Порт открыт; пробуем HTTP health через stdlib (в отдельном потоке — не блокируем loop).
        status = await asyncio.to_thread(_http_probe, port, path)
        if isinstance(status, int):
            if status < 500:
                return True, f"healthcheck OK: GET {path} → HTTP {status} (попытка {attempt + 1})"
            last_error = f"GET {path} → HTTP {status}"
        else:
            # Приложение слушает порт, но HTTP health не отвечает — считаем запуск успешным по TCP.
            return True, f"порт {port} отвечает по TCP (HTTP health недоступен: {status})"
        await asyncio.sleep(delay)

    return False, f"healthcheck провален после {retries} попыток: {last_error}"


def _http_probe(port: int, path: str) -> int | str:
    """Синхронный HTTP-запрос. Возвращает статус-код или текст ошибки."""
    import urllib.error
    import urllib.request

    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=3) as response:
            return response.status
    except urllib.error.HTTPError as exc:
        return exc.code
    except Exception as exc:
        return str(exc)
