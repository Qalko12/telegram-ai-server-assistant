"""AI-инструменты запуска кода в sandbox: тесты, линтер, форматтер, сборка,
установка зависимостей, запуск приложения (ТЗ §27).

Все исполнения — через coding.sandbox (изолированный контейнер с лимитами),
никогда напрямую на VPS. Уровни безопасности:
- run_tests / run_linter / run_formatter / run_build — SAFE (изолированы, сеть выключена
  по умолчанию: install/build получают сеть только внутри sandbox-контейнера, а не доступ к VPS);
- install_dependency — MODERATE (меняет состояние проекта, требует сеть);
- run_project — MODERATE (запускает приложение, слушает порт).

Автофикс-циклы (ТЗ §31) ограничивает общий CodeFixGuard: правки кода
(write/edit_code_file) увеличивают счётчик, прогоны тестов — нет; при исчерпании
лимита run_tests возвращает явное указание остановить автофикс.
"""

from pathlib import Path

from pydantic import BaseModel, Field

from ai.tools.registry import ExecutionContext, ToolSpec
from coding import tester
from coding.fix_guard import CodeFixGuard, FixLimitReachedError
from coding.sandbox import SandboxImageMissingError, run_in_sandbox
from coding.workspace import project_root, resolve_inside, set_project_status
from security.levels import SecurityLevel
from security.ratelimit import SANDBOX_RUNS, limiter

# Один guard на процесс: счётчики живут между tool-вызовами в рамках цикла агента.
fix_guard = CodeFixGuard()


async def _set_status(project: str, status: str) -> None:
    try:
        await set_project_status(project, status)
    except Exception:
        # Реестр проектов — справочная информация; его сбой не должен ронять прогон.
        pass


class ProjectTaskParams(BaseModel):
    project: str = Field(description="Имя проекта в Code Workspace.")


class InstallDependencyParams(BaseModel):
    project: str
    package: str = Field(description="Имя пакета, например 'fastapi' или 'fastapi==0.115.0'.")


class RunProjectParams(BaseModel):
    project: str
    entrypoint: str = Field(
        default="",
        description=(
            "Команда запуска внутри sandbox (sh -c), например 'python app/main.py' или 'npm start'. "
            "Пусто — автоопределение по языку проекта."
        ),
    )
    timeout_seconds: int = Field(default=60, ge=5, le=600)


async def _run_task(project: str, task: str, ctx: ExecutionContext) -> str:
    root = project_root(project)
    await limiter.acquire("sandbox_runs", ctx.telegram_user_id, SANDBOX_RUNS)
    try:
        result = await tester.run_task(root, task)
    except SandboxImageMissingError as exc:
        return f"⚠️ {exc}"

    text = tester.format_task_result(result, project, task)

    if task == "test":
        if result.success:
            # Успешный прогон завершает цикл автофикса.
            fix_guard.on_test_success(project)
            await _set_status(project, "tests_passed")
        else:
            fix_guard.on_test_failure(project)
            remaining = fix_guard.remaining(project)
            if remaining == 0:
                text += (
                    "\n\n⛔ ЛИМИТ АВТОИСПРАВЛЕНИЙ ИСЧЕРПАН: "
                    f"{fix_guard.limit} циклов правка→упавшие тесты подряд. "
                    "Дальнейшие правки кода этого проекта заблокированы. "
                    "Остановись и сообщи оператору, что не получилось и почему."
                )
            elif remaining <= 1:
                text += (
                    "\n\n⚠️ Приближается лимит автоисправлений "
                    f"(осталась {remaining} попытка из {fix_guard.limit}). "
                    "Если следующий прогон снова упадёт — автофикс будет остановлен."
                )
    if task == "build" and result.success:
        await _set_status(project, "build_ok")

    return text


async def handle_run_tests(params: ProjectTaskParams, ctx: ExecutionContext) -> str:
    return await _run_task(params.project, "test", ctx)


async def handle_run_linter(params: ProjectTaskParams, ctx: ExecutionContext) -> str:
    return await _run_task(params.project, "lint", ctx)


async def handle_run_formatter(params: ProjectTaskParams, ctx: ExecutionContext) -> str:
    return await _run_task(params.project, "format", ctx)


async def handle_run_build(params: ProjectTaskParams, ctx: ExecutionContext) -> str:
    return await _run_task(params.project, "build", ctx)


async def handle_install_dependency(params: InstallDependencyParams, ctx: ExecutionContext) -> str:
    root = project_root(params.project)
    language = tester.detect_language(root)
    await limiter.acquire("sandbox_runs", ctx.telegram_user_id, SANDBOX_RUNS)

    if language == "node":
        script = f"npm install --no-audit --no-fund {params.package!r} 2>&1"
    else:
        script = (
            f"python -m pip install --user {params.package!r} 2>&1 && "
            f"echo '{params.package}' >> requirements.txt && echo 'requirements.txt обновлён'"
        )

    try:
        result = await run_in_sandbox(root, script, language=language, network=True)
    except SandboxImageMissingError as exc:
        return f"⚠️ {exc}"

    from coding.sandbox import format_sandbox_result

    return format_sandbox_result(result, context=f"install_dependency({params.package}) в {params.project}")


async def handle_run_project(params: RunProjectParams, ctx: ExecutionContext) -> str:
    root = project_root(params.project)
    language = tester.detect_language(root)
    await limiter.acquire("sandbox_runs", ctx.telegram_user_id, SANDBOX_RUNS)

    entrypoint = params.entrypoint.strip()
    if not entrypoint:
        if language == "node":
            entrypoint = "npm start --silent 2>&1 || node index.js 2>&1"
        else:
            candidates = ["python main.py", "python app/main.py", "python -m app"]
            entrypoint = " || ".join(f"{c} 2>&1" for c in candidates)

    try:
        result = await run_in_sandbox(
            root, entrypoint, language=language, network=True, timeout=params.timeout_seconds
        )
    except SandboxImageMissingError as exc:
        return f"⚠️ {exc}"

    from coding.sandbox import format_sandbox_result

    text = format_sandbox_result(result, context=f"run_project({params.project})")
    if result.timed_out:
        text += (
            "\n\nПриложение работало до таймаута и было остановлено вместе с контейнером. "
            "Для долгоживущих приложений используй деплой (Docker/systemd), а не run_project."
        )
    elif result.success:
        await _set_status(params.project, "runs_ok")
    return text


RUN_TESTS = ToolSpec(
    name="run_tests",
    description=(
        "Запустить тесты проекта в изолированном Docker-sandbox (pytest для Python, npm test для Node). "
        "Возвращает вывод и exit code. Используется в цикле автоисправления: после правки кода — снова запусти тесты."
    ),
    input_model=ProjectTaskParams,
    handler=handle_run_tests,
    security_level=SecurityLevel.SAFE,
)

RUN_LINTER = ToolSpec(
    name="run_linter",
    description="Запустить линтер проекта в Docker-sandbox (ruff для Python, eslint для Node).",
    input_model=ProjectTaskParams,
    handler=handle_run_linter,
    security_level=SecurityLevel.SAFE,
)

RUN_FORMATTER = ToolSpec(
    name="run_formatter",
    description="Отформатировать код проекта в Docker-sandbox (ruff format / prettier).",
    input_model=ProjectTaskParams,
    handler=handle_run_formatter,
    security_level=SecurityLevel.SAFE,
)

RUN_BUILD = ToolSpec(
    name="run_build",
    description="Выполнить сборку/компиляцию проекта в Docker-sandbox (compileall для Python, npm run build для Node).",
    input_model=ProjectTaskParams,
    handler=handle_run_build,
    security_level=SecurityLevel.SAFE,
)

INSTALL_DEPENDENCY = ToolSpec(
    name="install_dependency",
    description=(
        "Установить пакет в окружение проекта внутри Docker-sandbox (pip/npm, с сетью). "
        "Для Python пакет также дописывается в requirements.txt проекта."
    ),
    input_model=InstallDependencyParams,
    handler=handle_install_dependency,
    security_level=SecurityLevel.MODERATE,
)

RUN_PROJECT = ToolSpec(
    name="run_project",
    description=(
        "Запустить приложение проекта в Docker-sandbox с лимитом времени (проверка старта/healthcheck). "
        "Контейнер останавливается по таймауту или завершении процесса. Для постоянного запуска — деплой."
    ),
    input_model=RunProjectParams,
    handler=handle_run_project,
    security_level=SecurityLevel.MODERATE,
)


def all_tester_tools() -> tuple[ToolSpec, ...]:
    return (RUN_TESTS, RUN_LINTER, RUN_FORMATTER, RUN_BUILD, INSTALL_DEPENDENCY, RUN_PROJECT)
