import re
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_SIZE_UNITS = {"B": 1, "KB": 1024, "MB": 1024**2, "GB": 1024**3}


def _parse_size(value: str) -> int:
    match = re.fullmatch(r"\s*(\d+)\s*([A-Za-z]+)\s*", value)
    if not match:
        raise ValueError(f"Invalid size string: {value!r}")
    number, unit = match.groups()
    unit = unit.upper()
    if unit not in _SIZE_UNITS:
        raise ValueError(f"Unknown size unit: {unit!r}")
    return int(number) * _SIZE_UNITS[unit]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    telegram_bot_token: str = Field(alias="TELEGRAM_BOT_TOKEN")
    anthropic_api_key: str = Field(alias="ANTHROPIC_API_KEY")
    # Пусто — официальный https://api.anthropic.com. Заполните для прокси/шлюза
    # с Anthropic-совместимым Messages API (/v1/messages).
    anthropic_base_url: str = Field(default="", alias="ANTHROPIC_BASE_URL")
    tavily_api_key: str = Field(default="", alias="TAVILY_API_KEY")
    claude_model_main: str = Field(default="claude-sonnet-4-5", alias="CLAUDE_MODEL_MAIN")
    claude_model_summary: str = Field(default="claude-haiku-4-5", alias="CLAUDE_MODEL_SUMMARY")
    allowed_telegram_ids_raw: str = Field(alias="ALLOWED_TELEGRAM_IDS")

    database_url: str = Field(default="sqlite+aiosqlite:///./data/bot.db", alias="DATABASE_URL")

    code_workspace: str = Field(default="/opt/ai-workspace", alias="CODE_WORKSPACE")
    allowed_paths_raw: str = Field(alias="ALLOWED_PATHS")
    backup_dir: str = Field(default="/var/backups/ai-assistant", alias="BACKUP_DIR")

    voice_responses_enabled: bool = Field(default=False, alias="VOICE_RESPONSES_ENABLED")
    voice_response_mode: Literal["text", "voice", "auto"] = Field(default="auto", alias="VOICE_RESPONSE_MODE")

    context_token_budget: int = Field(default=24000, alias="CONTEXT_TOKEN_BUDGET")
    history_keep_recent: int = Field(default=10, alias="HISTORY_KEEP_RECENT")
    history_max_messages: int = Field(default=30, alias="HISTORY_MAX_MESSAGES")
    summary_max_tokens: int = Field(default=600, alias="SUMMARY_MAX_TOKENS")

    monitor_check_interval_seconds: int = Field(default=30, alias="MONITOR_CHECK_INTERVAL_SECONDS")
    monitor_alert_cooldown_minutes: int = Field(default=30, alias="MONITOR_ALERT_COOLDOWN_MINUTES")

    sandbox_image_python: str = Field(default="ai-sandbox-python:latest", alias="SANDBOX_IMAGE_PYTHON")
    sandbox_image_node: str = Field(default="ai-sandbox-node:latest", alias="SANDBOX_IMAGE_NODE")
    sandbox_memory_limit: str = Field(default="256m", alias="SANDBOX_MEMORY_LIMIT")
    sandbox_cpu_limit: str = Field(default="1.0", alias="SANDBOX_CPU_LIMIT")
    sandbox_timeout_seconds: int = Field(default=300, alias="SANDBOX_TIMEOUT_SECONDS")

    max_agent_iterations: int = Field(default=30, alias="MAX_AGENT_ITERATIONS")

    max_command_timeout: int = Field(default=30, alias="MAX_COMMAND_TIMEOUT")
    max_output_size: int = Field(default=20000, alias="MAX_OUTPUT_SIZE")
    max_file_size: int = Field(default=20 * 1024 * 1024, alias="MAX_FILE_SIZE")
    max_code_fix_iterations: int = Field(default=5, alias="MAX_CODE_FIX_ITERATIONS")

    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    timezone: str = Field(default="UTC", alias="TIMEZONE")

    @property
    def allowed_telegram_ids(self) -> list[int]:
        return [int(part.strip()) for part in self.allowed_telegram_ids_raw.split(",") if part.strip()]

    @property
    def allowed_paths(self) -> list[str]:
        return [part.strip() for part in self.allowed_paths_raw.split(",") if part.strip()]

    @field_validator("max_file_size", mode="before")
    @classmethod
    def _parse_max_file_size(cls, value: object) -> object:
        if isinstance(value, str):
            return _parse_size(value)
        return value


settings = Settings()
