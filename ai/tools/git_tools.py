"""AI-инструменты Git (ТЗ §27, §33).

Уровни безопасности:
- git_status / git_diff / git_log — SAFE (только чтение);
- git_init / git_create_branch / git_checkout — MODERATE (меняют состояние репозитория);
- git_commit — MODERATE: всегда через подтверждение оператора (ТЗ §33: «Для важных
  проектов не делай commit в основную ветку автоматически»).
"""

from pydantic import BaseModel, Field

from ai.tools.registry import ExecutionContext, ToolSpec
from coding import git_ops
from coding.workspace import project_root
from security.levels import SecurityLevel


class ProjectParams(BaseModel):
    project: str = Field(description="Имя проекта в Code Workspace.")


class GitDiffParams(BaseModel):
    project: str
    staged: bool = Field(default=False, description="Показать уже добавленные в индекс изменения (--staged).")


class GitLogParams(BaseModel):
    project: str
    limit: int = Field(default=20, ge=1, le=100, description="Сколько последних коммитов показать.")


class GitBranchParams(BaseModel):
    project: str
    branch: str = Field(description="Имя ветки (латиница, цифры, '.', '_', '-', '/').")
    checkout: bool = Field(default=False, description="Сразу переключиться на созданную ветку.")


class GitCheckoutParams(BaseModel):
    project: str
    branch: str


class GitInitParams(BaseModel):
    project: str


class GitCommitParams(BaseModel):
    project: str
    message: str = Field(description="Сообщение коммита.")


async def handle_git_status(params: ProjectParams, ctx: ExecutionContext) -> str:
    root = project_root(params.project)
    return await git_ops.git_status(root) or "Рабочее дерево чистое."


async def handle_git_diff(params: GitDiffParams, ctx: ExecutionContext) -> str:
    root = project_root(params.project)
    diff = await git_ops.git_diff(root, staged=params.staged)
    return diff or "Изменений нет."


async def handle_git_log(params: GitLogParams, ctx: ExecutionContext) -> str:
    root = project_root(params.project)
    return await git_ops.git_log(root, limit=params.limit)


async def handle_git_init(params: GitInitParams, ctx: ExecutionContext) -> str:
    root = project_root(params.project)
    return await git_ops.git_init(root)


async def handle_git_create_branch(params: GitBranchParams, ctx: ExecutionContext) -> str:
    root = project_root(params.project)
    return await git_ops.git_create_branch(root, params.branch, checkout=params.checkout)


async def handle_git_checkout(params: GitCheckoutParams, ctx: ExecutionContext) -> str:
    root = project_root(params.project)
    return await git_ops.git_checkout(root, params.branch)


async def handle_git_commit(params: GitCommitParams, ctx: ExecutionContext) -> str:
    root = project_root(params.project)
    branch = await git_ops.git_current_branch(root)
    if git_ops.is_protected_branch(branch):
        # Не блокируем жёстко (подтверждение оператора уже получено), но предупреждаем в результате.
        result = await git_ops.git_commit_all(root, params.message)
        return (
            f"⚠️ Коммит сделан напрямую в основную ветку '{branch}'.\n{result}\n"
            "Рекомендация: для важных изменений используйте отдельную ветку (git_create_branch)."
        )
    return await git_ops.git_commit_all(root, params.message)


GIT_STATUS = ToolSpec(
    name="git_status",
    description="Показать git-статус проекта в Code Workspace (ветка, изменённые файлы).",
    input_model=ProjectParams,
    handler=handle_git_status,
    security_level=SecurityLevel.SAFE,
)

GIT_DIFF = ToolSpec(
    name="git_diff",
    description="Показать изменения в рабочем дереве проекта (или --staged).",
    input_model=GitDiffParams,
    handler=handle_git_diff,
    security_level=SecurityLevel.SAFE,
)

GIT_LOG = ToolSpec(
    name="git_log",
    description="Показать историю коммитов проекта.",
    input_model=GitLogParams,
    handler=handle_git_log,
    security_level=SecurityLevel.SAFE,
)

GIT_INIT = ToolSpec(
    name="git_init",
    description="Инициализировать git-репозиторий в проекте Code Workspace (ветка main).",
    input_model=GitInitParams,
    handler=handle_git_init,
    security_level=SecurityLevel.MODERATE,
)

GIT_CREATE_BRANCH = ToolSpec(
    name="git_create_branch",
    description="Создать ветку в репозитории проекта; опционально сразу переключиться на неё.",
    input_model=GitBranchParams,
    handler=handle_git_create_branch,
    security_level=SecurityLevel.MODERATE,
)

GIT_CHECKOUT = ToolSpec(
    name="git_checkout",
    description="Переключить проект на другую ветку.",
    input_model=GitCheckoutParams,
    handler=handle_git_checkout,
    security_level=SecurityLevel.MODERATE,
)

GIT_COMMIT = ToolSpec(
    name="git_commit",
    description=(
        "Закоммитить все изменения проекта (git add -A + git commit). Всегда требует "
        "подтверждения оператора. Перед коммитом покажи оператору git_diff."
    ),
    input_model=GitCommitParams,
    handler=handle_git_commit,
    security_level=SecurityLevel.MODERATE,
)


def all_git_tools() -> tuple[ToolSpec, ...]:
    return (
        GIT_STATUS,
        GIT_DIFF,
        GIT_LOG,
        GIT_INIT,
        GIT_CREATE_BRANCH,
        GIT_CHECKOUT,
        GIT_COMMIT,
    )
