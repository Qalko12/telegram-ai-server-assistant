# Sandbox-образ для запуска Python-кода и тестов проектов из Code Workspace.
# Сборка: docker build -f sandbox/python.Dockerfile -t ai-sandbox-python:latest sandbox/
FROM python:3.12-slim

RUN useradd -m -u 1000 sandbox
USER sandbox

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Тулинг предустановлен, чтобы тесты/линт не требовали сеть внутри sandbox.
RUN pip install --no-cache-dir --user pytest==8.3.4 pytest-asyncio==0.25.0 ruff==0.8.4

WORKDIR /workspace
CMD ["/bin/sh"]
