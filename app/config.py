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
    allowed_telegram_ids_raw: str = Field(alias="ALLOWED_TELEGRAM_IDS")

    database_url: str = Field(default="sqlite+aiosqlite:///./data/bot.db", alias="DATABASE_URL")

    code_workspace: str = Field(default="/opt/ai-workspace", alias="CODE_WORKSPACE")
    allowed_paths_raw: str = Field(alias="ALLOWED_PATHS")

    voice_responses_enabled: bool = Field(default=False, alias="VOICE_RESPONSES_ENABLED")
    voice_response_mode: Literal["text", "voice", "auto"] = Field(default="auto", alias="VOICE_RESPONSE_MODE")

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
