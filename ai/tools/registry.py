from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Optional

from aiogram import Bot
from pydantic import BaseModel

from security.levels import SecurityLevel


@dataclass
class ExecutionContext:
    telegram_user_id: int
    chat_id: int
    bot: Optional[Bot] = None  # Для отправки файлов в чат


ToolHandler = Callable[[BaseModel, ExecutionContext], Awaitable[str]]


@dataclass
class ToolSpec:
    name: str
    description: str
    input_model: type[BaseModel]
    handler: ToolHandler
    security_level: SecurityLevel


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        if spec.name in self._tools:
            raise ValueError(f"Tool already registered: {spec.name}")
        self._tools[spec.name] = spec

    def get(self, name: str) -> ToolSpec | None:
        return self._tools.get(name)

    def __contains__(self, name: str) -> bool:
        return name in self._tools

    def to_anthropic_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "name": spec.name,
                "description": spec.description,
                "input_schema": spec.input_model.model_json_schema(),
            }
            for spec in self._tools.values()
        ]
