"""Прогоны тестов/линта/форматтера/сборки проектов Code Workspace внутри sandbox.

Команды подбираются по языку проекта (определяется по маркерным файлам).
Все прогоны идут через coding.sandbox.run_in_sandbox — изолированно от VPS.
"""

from pathlib import Path

from coding.sandbox import SandboxResult, format_sandbox_result, run_in_sandbox


def detect_language(project_path: Path) -> str:
    if (project_path / "package.json").exists():
        return "node"
    return "python"


# Скрипты для sandbox. set -e не используется намеренно: нам нужен вывод и точный
# exit code конкретной команды, а не обрыв на первом же ненулевом коде.
PYTHON_SCRIPTS = {
    "test": "python -m pytest tests/ -v --tb=short 2>&1 || python -m pytest -v --tb=short 2>&1",
    "lint": "ruff check . 2>&1",
    "format": "ruff format . 2>&1 && ruff check --fix . 2>&1",
    "build": "python -m compileall -q . 2>&1",
}

NODE_SCRIPTS = {
    "test": "npm test --silent 2>&1 || npx --yes jest --silent 2>&1",
    "lint": "npx --yes eslint . 2>&1 || true",
    "format": "npx --yes prettier --write . 2>&1",
    "build": "npm run build --silent 2>&1",
}

# Операции, которым нужна сеть: установка зависимостей и npm-сборка с внешними пакетами.
_NETWORK_REQUIRED = {"install", "build"}


async def run_task(
    project_path: Path,
    task: str,
    *,
    language: str | None = None,
    network: bool | None = None,
    timeout: int | None = None,
) -> SandboxResult:
    lang = language or detect_language(project_path)
    scripts = NODE_SCRIPTS if lang == "node" else PYTHON_SCRIPTS

    if task == "install":
        script = "npm install --no-audit --no-fund 2>&1" if lang == "node" else (
            "python -m pip install --user -r requirements.txt 2>&1"
            if (project_path / "requirements.txt").exists()
            else "echo 'requirements.txt не найден — нечего устанавливать'"
        )
    elif task in scripts:
        script = scripts[task]
    else:
        raise ValueError(f"Неизвестная задача: {task!r}. Доступны: test, lint, format, build, install.")

    allow_network = network if network is not None else task in _NETWORK_REQUIRED

    return await run_in_sandbox(
        project_path,
        script,
        language=lang,
        network=allow_network,
        timeout=timeout,
    )


def format_task_result(result: SandboxResult, project: str, task: str) -> str:
    return format_sandbox_result(result, context=f"{task} в проекте {project}")
