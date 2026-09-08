# Telegram AI Server & Coding Assistant
# Контейнеру нужны CLI-инструменты, которыми бот управляет хостом:
# - docker-ce-cli: управление контейнерами через примонтированный /var/run/docker.sock
# - git: git-операции в Code Workspace
# - systemd: systemctl/journalctl работают против хоста через примонтированный
#   /run/systemd/private и журналы (см. docker-compose.yml)
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        git \
        curl \
        ca-certificates \
        gnupg \
        systemd \
        procps \
    && install -d /etc/apt/keyrings \
    && curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc \
    && chmod a+r /etc/apt/keyrings/docker.asc \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/debian bookworm stable" \
        > /etc/apt/sources.list.d/docker.list \
    && apt-get update && apt-get install -y --no-install-recommends docker-ce-cli \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# На случай CRLF-окончаний при клонировании на Windows: приводим скрипт к LF.
RUN sed -i 's/\r$//' /app/docker/entrypoint.sh \
    && chmod +x /app/docker/entrypoint.sh

ENTRYPOINT ["/app/docker/entrypoint.sh"]
