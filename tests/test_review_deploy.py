"""Фаза 11: code review материал + генерация артефактов деплоя + healthcheck."""

import asyncio
import socket
import threading
from unittest.mock import AsyncMock

import pytest

import ai.tools.deploy_tools as deploy_tools_module
from ai.tools.deploy_tools import (
    DEPLOY_PROJECT,
    PREPARE_DEPLOYMENT,
    REVIEW_PROJECT,
    DeployProjectParams,
    PrepareDeploymentParams,
    ReviewProjectParams,
    handle_deploy_project,
    handle_prepare_deployment,
    handle_review_project,
)
from ai.tools.registry import ExecutionContext
from coding.deploy import healthcheck, prepare_all
from coding.review import collect_review_material
from security.levels import SecurityLevel
from server.executor import CommandResult


CTX = ExecutionContext(telegram_user_id=42, chat_id=42)


@pytest.fixture(autouse=True)
def _workspace(tmp_path, monkeypatch):
    from app.config import settings as app_settings

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setattr(app_settings, "code_workspace", str(workspace))
    monkeypatch.setattr(deploy_tools_module, "set_project_status", AsyncMock())
    return workspace


@pytest.fixture
def python_project(_workspace):
    root = _workspace / "fastapi-app"
    (root / "app").mkdir(parents=True)
    (root / "requirements.txt").write_text("fastapi\nuvicorn\n", encoding="utf-8")
    (root / "app" / "main.py").write_text(
        "API_KEY = 'sk-secret-123'  # плохая практика\nprint('hello')\n", encoding="utf-8"
    )
    (root / "README.md").write_text("# fastapi-app\n", encoding="utf-8")
    return root


# ---------- review ----------


def test_collect_review_material_contains_structure_and_code(python_project) -> None:
    material = collect_review_material(python_project)

    assert "STRUCTURE:" in material
    assert "app/main.py" in material
    assert "FILE CONTENTS:" in material
    assert "sk-secret-123" in material  # секрет виден Claude — он должен его отметить


def test_collect_review_material_skips_service_dirs(python_project) -> None:
    (python_project / "__pycache__").mkdir()
    (python_project / "__pycache__" / "junk.pyc").write_bytes(b"\x00\x01")
    (python_project / "node_modules").mkdir()
    (python_project / "node_modules" / "lib.js").write_text("x", encoding="utf-8")

    material = collect_review_material(python_project)

    assert "__pycache__" not in material
    assert "node_modules" not in material


def test_collect_review_material_empty_project(_workspace) -> None:
    root = _workspace / "empty"
    root.mkdir()
    assert "пуст" in collect_review_material(root).lower()


def test_collect_review_material_truncates_huge_files(python_project) -> None:
    (python_project / "big.py").write_text("x" * 200_000, encoding="utf-8")

    material = collect_review_material(python_project)

    assert "обрезан" in material
    assert len(material) < 150_000


async def test_review_project_tool_output(python_project) -> None:
    result = await handle_review_project(
        ReviewProjectParams(project="fastapi-app", focus="безопасность"), CTX
    )

    assert "Critical" in result
    assert "безопасность" in result
    assert "sk-secret-123" in result


def test_deploy_tool_security_levels() -> None:
    assert REVIEW_PROJECT.security_level == SecurityLevel.SAFE
    assert PREPARE_DEPLOYMENT.security_level == SecurityLevel.MODERATE
    assert DEPLOY_PROJECT.security_level == SecurityLevel.CRITICAL


# ---------- подготовка артефактов ----------


def test_prepare_all_generates_artifacts(python_project) -> None:
    created = prepare_all(python_project, project_name="fastapi-app", port=8000)

    deploy_dir = python_project / "deploy"
    assert (deploy_dir / "Dockerfile").exists()
    assert (deploy_dir / "docker-compose.yml").exists()
    assert (deploy_dir / "fastapi-app.service").exists()
    assert (deploy_dir / "fastapi-app.nginx.conf").exists()
    assert (python_project / ".env.example").exists()
    assert len(created) == 5

    dockerfile = (deploy_dir / "Dockerfile").read_text(encoding="utf-8")
    assert "python:3.12-slim" in dockerfile
    assert "HEALTHCHECK" in dockerfile
    assert "EXPOSE 8000" in dockerfile

    compose = (deploy_dir / "docker-compose.yml").read_text(encoding="utf-8")
    assert "127.0.0.1:8000:8000" in compose
    assert "restart: unless-stopped" in compose

    unit = (deploy_dir / "fastapi-app.service").read_text(encoding="utf-8")
    assert "[Unit]" in unit and "[Service]" in unit and "[Install]" in unit
    assert "NoNewPrivileges=true" in unit

    nginx = (deploy_dir / "fastapi-app.nginx.conf").read_text(encoding="utf-8")
    assert "proxy_pass http://127.0.0.1:8000" in nginx


def test_prepare_all_for_node_project(_workspace) -> None:
    root = _workspace / "web"
    root.mkdir()
    (root / "package.json").write_text('{"name":"web"}', encoding="utf-8")

    prepare_all(root, project_name="web", port=3000)

    dockerfile = (root / "deploy" / "Dockerfile").read_text(encoding="utf-8")
    assert "node:20-alpine" in dockerfile
    assert "npm ci" in dockerfile


def test_prepare_all_preserves_existing_env_example(python_project) -> None:
    (python_project / ".env.example").write_text("MY_VAR=1\n", encoding="utf-8")

    created = prepare_all(python_project, project_name="fastapi-app")

    assert ".env.example" not in created
    assert (python_project / ".env.example").read_text(encoding="utf-8") == "MY_VAR=1\n"


async def test_prepare_deployment_tool(python_project) -> None:
    result = await handle_prepare_deployment(
        PrepareDeploymentParams(project="fastapi-app", port=9000), CTX
    )

    assert "Dockerfile" in result
    assert "docker-compose.yml" in result
    assert "9000" in result
    assert (python_project / "deploy" / "Dockerfile").exists()


# ---------- деплой ----------


async def test_deploy_project_success_flow(python_project, monkeypatch) -> None:
    prepare_all(python_project, project_name="fastapi-app", port=8000)

    monkeypatch.setattr(
        deploy_tools_module.deploy,
        "build_and_start_container",
        AsyncMock(return_value="Образ собран, контейнер ai-fastapi-app запущен."),
    )
    monkeypatch.setattr(
        deploy_tools_module.deploy, "healthcheck", AsyncMock(return_value=(True, "healthcheck OK: GET /health → HTTP 200"))
    )

    result = await handle_deploy_project(DeployProjectParams(project="fastapi-app", port=8000), CTX)

    assert "✅ Деплой выполнен" in result
    assert "healthcheck OK" in result


async def test_deploy_project_build_failure(python_project, monkeypatch) -> None:
    prepare_all(python_project, project_name="fastapi-app")

    from coding.deploy import DeployArtifactError

    monkeypatch.setattr(
        deploy_tools_module.deploy,
        "build_and_start_container",
        AsyncMock(side_effect=DeployArtifactError("ошибка сборки: нет pip")),
    )

    result = await handle_deploy_project(DeployProjectParams(project="fastapi-app", port=8000), CTX)

    assert "❌ Деплой не удался" in result
    assert "ошибка сборки" in result


async def test_deploy_project_healthcheck_failure(python_project, monkeypatch) -> None:
    prepare_all(python_project, project_name="fastapi-app")

    monkeypatch.setattr(
        deploy_tools_module.deploy,
        "build_and_start_container",
        AsyncMock(return_value="контейнер запущен"),
    )
    monkeypatch.setattr(
        deploy_tools_module.deploy, "healthcheck", AsyncMock(return_value=(False, "healthcheck провален после 6 попыток"))
    )

    result = await handle_deploy_project(DeployProjectParams(project="fastapi-app", port=8000), CTX)

    assert "healthcheck не прошёл" in result
    assert "docker_logs" in result


# ---------- healthcheck (настоящий) ----------


async def test_healthcheck_tcp_only_port() -> None:
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    port = server.getsockname()[1]

    def _accept_loop():
        try:
            while True:
                conn, _ = server.accept()
                conn.close()
        except OSError:
            pass

    thread = threading.Thread(target=_accept_loop, daemon=True)
    thread.start()

    try:
        ok, text = await healthcheck(port, retries=2, delay=0.1)
        assert ok is True
        assert "TCP" in text or "HTTP" in text
    finally:
        server.close()


async def test_healthcheck_fails_on_closed_port() -> None:
    closed = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    closed.bind(("127.0.0.1", 0))
    port = closed.getsockname()[1]
    closed.close()

    ok, text = await healthcheck(port, retries=2, delay=0.05)

    assert ok is False
    assert "провален" in text
