# Sandbox-образ для запуска Node.js-кода и тестов проектов из Code Workspace.
# Сборка: docker build -f sandbox/node.Dockerfile -t ai-sandbox-node:latest sandbox/
FROM node:20-alpine

# В node:20-alpine uid 1000 уже занят пользователем node — переиспользуем его как
# sandbox-пользователя (его и запускает контейнер: --user 1000:1000).
USER node

ENV npm_config_cache=/tmp/.npm

WORKDIR /workspace
CMD ["/bin/sh"]
