"""Git-операции для проектов Code Workspace (ТЗ §33).

Git вызывается через CLI и общий CommandExecutor (git status/diff/log/branch/
checkout/commit). Все операции строго в пределах директории проекта; аргументы
передаются списком без shell-интерпретации. Коммит в основную ветку автоматически
не делается — только через подтверждение оператора (уровень инструмента MODERATE).
"""

import re

from coding.workspace import WorkspaceError
from server.executor import CommandExecutor, CommandResult

_BRANCH_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,127}$")

# Аргументы, начинающиеся с '-', могут быть интерпретированы git как опции
# (например, '--exec=...'). Разделитель '--' защищает от argument injection.
_MAIN_PROTECTED_BRANCHES = {"main", "master"}


class GitError(WorkspaceError):
    pass


def validate_branch_name(name: str) -> str:
    if not _BRANCH_PATTERN.match(name):
        raise GitError(f"Недопустимое имя ветки: {name!r}")
    if name.startswith("-"):
        raise GitError(f"Имя ветки не должно начинаться с '-': {name!r}")
    return name


def validate_commit_message(message: str) -> str:
    message = message.strip()
    if not message:
        raise GitError("Сообщение коммита не может быть пустым.")
    if len(message) > 4000:
        raise GitError("Сообщение коммита слишком длинное (максимум 4000 символов).")
    return message


async def _git(project_path, args: list[str], executor: CommandExecutor | None = None) -> CommandResult:
    executor = executor or CommandExecutor(timeout=60)
    return await executor.run("git", ["-C", str(project_path), *args])


async def is_git_repo(project_path, executor: CommandExecutor | None = None) -> bool:
    result = await _git(project_path, ["rev-parse", "--is-inside-work-tree"], executor)
    return result.success and result.stdout.strip() == "true"


async def ensure_git_repo(project_path, executor: CommandExecutor | None = None) -> None:
    if not await is_git_repo(project_path, executor):
        raise GitError(
            f"Проект не является git-репозиторием: {project_path}. "
            "Инициализируйте его (git_init) или проверьте имя проекта."
        )


async def git_init(project_path, executor: CommandExecutor | None = None) -> str:
    if await is_git_repo(project_path, executor):
        return "Проект уже является git-репозиторием."
    result = await _git(project_path, ["init"], executor)
    if not result.success:
        raise GitError(f"git init завершился с ошибкой: {result.stderr or result.stdout}")
    # Задаём ветку по умолчанию: symbolic-ref работает на пустом репозитории,
    # в отличие от checkout -b, и не зависит от init.defaultBranch хоста.
    await _git(project_path, ["symbolic-ref", "HEAD", "refs/heads/main"], executor)
    return f"Git-репозиторий инициализирован: {project_path} (ветка main)."


async def git_status(project_path, executor: CommandExecutor | None = None) -> str:
    await ensure_git_repo(project_path, executor)
    result = await _git(project_path, ["status", "--porcelain", "-b"], executor)
    return _output(result)


async def git_diff(project_path, staged: bool = False, executor: CommandExecutor | None = None) -> str:
    await ensure_git_repo(project_path, executor)
    args = ["diff"] + (["--staged"] if staged else [])
    result = await _git(project_path, args, executor)
    return _output(result)


async def git_log(project_path, limit: int = 20, executor: CommandExecutor | None = None) -> str:
    await ensure_git_repo(project_path, executor)
    result = await _git(
        project_path,
        ["log", f"-{limit}", "--pretty=format:%h %ad %s", "--date=short"],
        executor,
    )
    if result.exit_code != 0 and "does not have any commits" in (result.stderr + result.stdout):
        return "В репозитории ещё нет коммитов."
    return _output(result)


async def git_create_branch(project_path, branch: str, checkout: bool = False, executor: CommandExecutor | None = None) -> str:
    await ensure_git_repo(project_path, executor)
    validate_branch_name(branch)
    args = ["checkout", "-b", branch] if checkout else ["branch", branch]
    result = await _git(project_path, args, executor)
    return _output(result) or f"Ветка {branch} создана."


async def git_checkout(project_path, branch: str, executor: CommandExecutor | None = None) -> str:
    await ensure_git_repo(project_path, executor)
    validate_branch_name(branch)
    result = await _git(project_path, ["checkout", branch], executor)
    return _output(result) or f"Переключено на ветку {branch}."


async def git_current_branch(project_path, executor: CommandExecutor | None = None) -> str:
    await ensure_git_repo(project_path, executor)
    result = await _git(project_path, ["rev-parse", "--abbrev-ref", "HEAD"], executor)
    branch = result.stdout.strip()
    if not branch or branch == "HEAD":
        # Пустой репозиторий без коммитов: читаем ссылку напрямую.
        ref = await _git(project_path, ["symbolic-ref", "--short", "-q", "HEAD"], executor)
        branch = ref.stdout.strip()
    return branch or "unknown"


async def git_commit_all(
    project_path, message: str, executor: CommandExecutor | None = None
) -> str:
    """Добавляет все изменения и создаёт коммит. Вызывается только после подтверждения оператора."""
    await ensure_git_repo(project_path, executor)
    validate_commit_message(message)

    add_result = await _git(project_path, ["add", "-A"], executor)
    if not add_result.success:
        raise GitError(f"git add failed: {add_result.stderr or add_result.stdout}")

    branch = await git_current_branch(project_path, executor)

    commit_result = await _git(project_path, ["commit", "-m", message], executor)
    if commit_result.exit_code != 0:
        combined = commit_result.stderr + commit_result.stdout
        if "nothing to commit" in combined:
            return "Нет изменений для коммита."
        raise GitError(f"git commit failed: {combined}")

    short_stat = await _git(project_path, ["show", "--stat", "--oneline", "-s", "HEAD"], executor)
    return f"Коммит создан в ветке '{branch}': {message}\n{short_stat.stdout.strip()}"


def is_protected_branch(branch: str) -> bool:
    return branch.strip().lower() in _MAIN_PROTECTED_BRANCHES


def _output(result: CommandResult) -> str:
    output = (result.stdout or "").strip()
    error = (result.stderr or "").strip()
    if result.exit_code != 0 and error:
        raise GitError(f"git завершился с ошибкой (exit={result.exit_code}): {error}")
    return output
