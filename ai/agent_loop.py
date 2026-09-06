import logging
from typing import Any

from ai.client import get_client
from ai.prompts import SYSTEM_PROMPT, wrap_untrusted
from ai.tools.registry import ExecutionContext, ToolRegistry
from app.config import settings
from security.levels import SecurityLevel

logger = logging.getLogger(__name__)

MAX_AGENT_ITERATIONS = 15
MAX_RESPONSE_TOKENS = 2048


class AgentLoop:
    def __init__(self, registry: ToolRegistry) -> None:
        self._registry = registry

    async def run(self, messages: list[dict[str, Any]], ctx: ExecutionContext) -> str:
        client = get_client()
        conversation = list(messages)

        for _ in range(MAX_AGENT_ITERATIONS):
            response = await client.messages.create(
                model=settings.claude_model_main,
                max_tokens=MAX_RESPONSE_TOKENS,
                system=SYSTEM_PROMPT,
                tools=self._registry.to_anthropic_tools(),
                messages=conversation,
            )

            conversation.append({"role": "assistant", "content": response.content})

            if response.stop_reason != "tool_use":
                return _extract_text(response.content)

            tool_results = [await self._run_tool_block(block, ctx) for block in response.content if block.type == "tool_use"]
            conversation.append({"role": "user", "content": tool_results})

        return "Достигнут лимит итераций агента, не смог завершить задачу за отведённое число шагов."

    async def _run_tool_block(self, block: Any, ctx: ExecutionContext) -> dict[str, Any]:
        spec = self._registry.get(block.name)

        if spec is None:
            return _tool_error(block.id, f"Unknown tool: {block.name}")

        if spec.security_level != SecurityLevel.SAFE:
            return _tool_error(
                block.id,
                f"Tool '{block.name}' requires user confirmation (level={spec.security_level.value}), "
                "which is not yet wired into this version of the agent loop.",
            )

        try:
            params = spec.input_model.model_validate(block.input)
            result_text = await spec.handler(params, ctx)
        except Exception as exc:
            logger.exception("Tool %s failed", block.name)
            return _tool_error(block.id, str(exc))

        wrapped = wrap_untrusted(block.name, result_text)
        return {"type": "tool_result", "tool_use_id": block.id, "content": wrapped}


def _extract_text(content: list[Any]) -> str:
    parts = [block.text for block in content if block.type == "text"]
    return "\n".join(parts) if parts else ""


def _tool_error(tool_use_id: str, message: str) -> dict[str, Any]:
    return {"type": "tool_result", "tool_use_id": tool_use_id, "content": message, "is_error": True}
