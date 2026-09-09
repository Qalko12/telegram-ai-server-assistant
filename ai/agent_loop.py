import logging
from dataclasses import dataclass, field
from typing import Any, Literal

from ai.client import get_client
from ai.prompts import SYSTEM_PROMPT, wrap_untrusted
from ai.tools.registry import ExecutionContext, ToolRegistry
from app.config import settings
from security.levels import SecurityLevel
from security.ratelimit import RateLimitExceeded

logger = logging.getLogger(__name__)

MAX_RESPONSE_TOKENS = 2048


@dataclass
class AgentFinalAnswer:
    text: str
    kind: Literal["final"] = "final"


@dataclass
class AgentConfirmationNeeded:
    tool_use_id: str
    tool_name: str
    arguments: dict[str, Any]
    reason: str
    snapshot: list[dict[str, Any]]
    pending_tool_results: list[dict[str, Any]] = field(default_factory=list)
    kind: Literal["confirmation_needed"] = "confirmation_needed"


AgentOutcome = AgentFinalAnswer | AgentConfirmationNeeded


class AgentLoop:
    def __init__(self, registry: ToolRegistry) -> None:
        self.registry = registry

    async def run(self, messages: list[dict[str, Any]], ctx: ExecutionContext) -> AgentOutcome:
        return await self._loop(list(messages), ctx)

    async def resume(
        self,
        pending: AgentConfirmationNeeded,
        result_content: str,
        *,
        is_error: bool,
        ctx: ExecutionContext,
    ) -> AgentOutcome:
        resolved_block = {
            "type": "tool_result",
            "tool_use_id": pending.tool_use_id,
            "content": result_content,
            "is_error": is_error,
        }
        conversation = list(pending.snapshot)
        conversation.append({"role": "user", "content": [*pending.pending_tool_results, resolved_block]})
        return await self._loop(conversation, ctx)

    async def _loop(self, conversation: list[dict[str, Any]], ctx: ExecutionContext) -> AgentOutcome:
        client = get_client()

        for iteration in range(settings.max_agent_iterations):
            try:
                response = await client.messages.create(
                    model=settings.claude_model_main,
                    max_tokens=MAX_RESPONSE_TOKENS,
                    system=SYSTEM_PROMPT,
                    tools=self.registry.to_anthropic_tools(),
                    messages=conversation,
                )
            except Exception as exc:
                logger.exception("Claude API call failed on iteration %d", iteration)
                # Возвращаем ошибку как финальный ответ — не роняем весь ход.
                return AgentFinalAnswer(
                    text=f"⚠️ Ошибка API Claude: {type(exc).__name__}. Попробуй ещё раз или проверь ключ/баланс."
                )

            assistant_blocks = [block.model_dump() for block in response.content]
            conversation.append({"role": "assistant", "content": assistant_blocks})

            if response.stop_reason != "tool_use":
                return AgentFinalAnswer(text=_extract_text(response.content))

            tool_results: list[dict[str, Any]] = []
            pending: AgentConfirmationNeeded | None = None

            for block in response.content:
                if block.type != "tool_use":
                    continue

                spec = self.registry.get(block.name)

                if spec is None:
                    tool_results.append(_tool_error(block.id, f"Unknown tool: {block.name}"))
                    continue

                if spec.security_level != SecurityLevel.SAFE:
                    if pending is None:
                        pending = AgentConfirmationNeeded(
                            tool_use_id=block.id,
                            tool_name=block.name,
                            arguments=block.input,
                            reason=_extract_text(response.content) or f"Требуется выполнить '{block.name}'.",
                            snapshot=list(conversation),
                        )
                    else:
                        tool_results.append(
                            _tool_error(
                                block.id,
                                "Another action in this turn already requires confirmation; only one "
                                "pending confirmation is supported at a time. Wait for it to resolve first.",
                            )
                        )
                    continue

                try:
                    params = spec.input_model.model_validate(block.input)
                    result_text = await spec.handler(params, ctx)
                except RateLimitExceeded as exc:
                    tool_results.append(
                        _tool_error(
                            block.id,
                            f"Rate limit: слишком много действий этой категории. "
                            f"Повторить можно через ~{exc.retry_after_seconds} секунд. "
                            "Сообщи это пользователю и не повторяй вызов сразу.",
                        )
                    )
                    continue
                except Exception as exc:
                    logger.exception("Tool %s failed", block.name)
                    tool_results.append(_tool_error(block.id, str(exc)))
                    continue

                wrapped = wrap_untrusted(block.name, result_text)
                tool_results.append({"type": "tool_result", "tool_use_id": block.id, "content": wrapped})

            if pending is not None:
                pending.pending_tool_results = tool_results
                return pending

            conversation.append({"role": "user", "content": tool_results})

        return AgentFinalAnswer(text="Достигнут лимит итераций агента, не смог завершить задачу за отведённое число шагов.")


def _extract_text(content: list[Any]) -> str:
    parts = [block.text for block in content if block.type == "text"]
    return "\n".join(parts) if parts else ""


def _tool_error(tool_use_id: str, message: str) -> dict[str, Any]:
    # Ошибки тоже могут содержать данные из файлов/HTTP/команд — оборачиваем в untrusted.
    return {
        "type": "tool_result",
        "tool_use_id": tool_use_id,
        "content": wrap_untrusted("error", message),
        "is_error": True,
    }
