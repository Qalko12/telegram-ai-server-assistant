"""AI-инструменты code review и деплоя (ТЗ §34, §35).

- review_project — SAFE: собирает снимок проекта, ревью делает Claude в основном цикле.
- prepare_deployment — MODERATE: генерирует артефакты (Dockerfile, compose, systemd,
  nginx, .env.example) в deploy/ внутри проекта.
- deploy_project — CRITICAL: сборка образа и запуск контейнера на VPS, всегда через
  подтверждение; включает healthcheck после запуска.
"""

from pydantic import BaseModel, Field

from ai.tools.registry import ExecutionContext, ToolSpec
from coding import deploy
from coding.review import collect_review_material
from coding.workspace import project_root, set_project_status
from security.levels import SecurityLevel


class ReviewProjectParams(BaseModel):
    project: str = Field(description="Имя проекта в Code Workspace.")
    focus: str = Field(default="", description="На что обратить особое внимание, например 'безопасность' или 'производительность'.")


class PrepareDeploymentParams(BaseModel):
    project: str
    port: int = Field(default=8000, ge=1, le=65535, description="Порт, который слушает приложение.")


class DeployProjectParams(BaseModel):
    project: str
    port: int = Field(default=8000, ge=1, le=65535)


async def handle_review_project(params: ReviewProjectParams, ctx: ExecutionContext) -> str:
    root = project_root(params.project)
    material = collect_review_material(root)
    header = "Проведи code review этого проекта и выдай результат строго в формате:\n"
    header += "🔴 Critical / 🟠 High / 🟡 Medium / 🟢 Low — по категориям: баги, безопасность (включая захардкоженные секреты), архитектура, производительность, обработка ошибок, зависимости.\n"
    if params.focus.strip():
        header += f"Особое внимание оператора: {params.focus.strip()}\n"
    return f"{header}\n{material}"


async def handle_prepare_deployment(params: PrepareDeploymentParams, ctx: ExecutionContext) -> str:
    root = project_root(params.project)
    created = deploy.prepare_all(root, project_name=params.project, port=params.port)
    return (
        f"Артефакты деплоя созданы в {params.project}/deploy/:\n"
        + "\n".join(f"• {name}" for name in created)
        + f"\n\nПорт приложения: {params.port}. Контейнер публикуется только на 127.0.0.1; "
        "для внешнего доступа настрой nginx (фрагмент конфига в deploy/)."
    )


async def handle_deploy_project(params: DeployProjectParams, ctx: ExecutionContext) -> str:
    root = project_root(params.project)

    try:
        started = await deploy.build_and_start_container(
            root, project_name=params.project, port=params.port
        )
    except deploy.DeployArtifactError as exc:
        return f"❌ Деплой не удался:\n{exc}"

    ok, health = await deploy.healthcheck(params.port)

    if ok:
        await set_project_status(params.project, "deployed")
        return f"✅ Деплой выполнен.\n{started}\n\nHealthcheck: {health}"

    await set_project_status(params.project, "deploy_failed")
    logs_hint = f"Посмотри логи: docker_logs('{params.project}') — нет, контейнер называется 'ai-{params.project}', используй docker_logs с этим именем."
    return f"⚠️ Контейнер запущен, но healthcheck не прошёл.\n{started}\n\nHealthcheck: {health}\n{logs_hint}"


REVIEW_PROJECT = ToolSpec(
    name="review_project",
    description=(
        "Собрать материал для code review проекта: структуру и содержимое ключевых файлов. "
        "После получения материала проведи ревью сам: ищи баги, security issues, плохую архитектуру, "
        "проблемы производительности, отсутствие обработки ошибок, проблемы зависимостей, "
        "захардкоженные секреты. Ответ оформляй по severity: 🔴 Critical, 🟠 High, 🟡 Medium, 🟢 Low."
    ),
    input_model=ReviewProjectParams,
    handler=handle_review_project,
    security_level=SecurityLevel.SAFE,
)

PREPARE_DEPLOYMENT = ToolSpec(
    name="prepare_deployment",
    description=(
        "Подготовить проект к деплою: сгенерировать Dockerfile, docker-compose.yml, systemd unit, "
        "nginx-конфиг и .env.example в папке deploy/ проекта. Сам запуск — отдельным инструментом deploy_project."
    ),
    input_model=PrepareDeploymentParams,
    handler=handle_prepare_deployment,
    security_level=SecurityLevel.MODERATE,
)

DEPLOY_PROJECT = ToolSpec(
    name="deploy_project",
    description=(
        "Задеплоить проект на VPS: собрать Docker-образ, запустить контейнер (127.0.0.1:port, лимиты памяти/CPU) "
        "и выполнить healthcheck. ПРОДАКШН-ОПЕРАЦИЯ: всегда требует подтверждения оператора."
    ),
    input_model=DeployProjectParams,
    handler=handle_deploy_project,
    security_level=SecurityLevel.CRITICAL,
)


def all_deploy_tools() -> tuple[ToolSpec, ...]:
    return (REVIEW_PROJECT, PREPARE_DEPLOYMENT, DEPLOY_PROJECT)
