# Sandbox-образ для запуска Node.js-кода и тестов проектов из Code Workspace.
# Сборка: docker build -f sandbox/node.Dockerfile -t ai-sandbox-node:latest sandbox/
FROM node:20-alpine

RUN adduser -D -u 1000 sandbox
USER sandbox

ENV npm_config_cache=/tmp/.npm

WORKDIR /workspace
CMD ["/bin/sh"]
