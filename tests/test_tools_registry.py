import pytest
from pydantic import BaseModel

from ai.tools.registry import ExecutionContext, ToolRegistry, ToolSpec
from security.levels import SecurityLevel


class _DummyParams(BaseModel):
    value: int = 0


async def _dummy_handler(params: _DummyParams, ctx: ExecutionContext) -> str:
    return f"dummy:{params.value}"


def _dummy_spec(name: str = "dummy_tool") -> ToolSpec:
    return ToolSpec(
        name=name,
        description="A dummy tool for testing.",
        input_model=_DummyParams,
        handler=_dummy_handler,
        security_level=SecurityLevel.SAFE,
    )


def test_register_and_get() -> None:
    registry = ToolRegistry()
    registry.register(_dummy_spec())

    spec = registry.get("dummy_tool")
    assert spec is not None
    assert spec.security_level == SecurityLevel.SAFE
    assert "dummy_tool" in registry


def test_get_missing_tool_returns_none() -> None:
    registry = ToolRegistry()
    assert registry.get("does_not_exist") is None


def test_duplicate_registration_raises() -> None:
    registry = ToolRegistry()
    registry.register(_dummy_spec())

    with pytest.raises(ValueError, match="already registered"):
        registry.register(_dummy_spec())


def test_to_anthropic_tools_shape() -> None:
    registry = ToolRegistry()
    registry.register(_dummy_spec())

    tools = registry.to_anthropic_tools()

    assert len(tools) == 1
    assert tools[0]["name"] == "dummy_tool"
    assert tools[0]["input_schema"]["type"] == "object"
    assert "value" in tools[0]["input_schema"]["properties"]
