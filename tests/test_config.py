from app.config import Settings


def _make_settings(**overrides: str) -> Settings:
    values = {
        "TELEGRAM_BOT_TOKEN": "test-token",
        "ANTHROPIC_API_KEY": "test-key",
        "ALLOWED_TELEGRAM_IDS": "111, 222",
        "ALLOWED_PATHS": "/opt, /var/www",
        "MAX_FILE_SIZE": "5MB",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_allowed_telegram_ids_parsed_as_int_list() -> None:
    settings = _make_settings()
    assert settings.allowed_telegram_ids == [111, 222]


def test_allowed_paths_parsed_as_list() -> None:
    settings = _make_settings()
    assert settings.allowed_paths == ["/opt", "/var/www"]


def test_max_file_size_parsed_to_bytes() -> None:
    settings = _make_settings(MAX_FILE_SIZE="2GB")
    assert settings.max_file_size == 2 * 1024**3


def test_max_file_size_default_unit_bytes() -> None:
    settings = _make_settings(MAX_FILE_SIZE="100B")
    assert settings.max_file_size == 100


def test_memory_settings_defaults_and_overrides() -> None:
    settings = _make_settings()
    assert settings.context_token_budget == 24000
    assert settings.history_keep_recent == 10
    assert settings.history_max_messages == 30
    assert settings.summary_max_tokens == 600

    custom = _make_settings(
        CONTEXT_TOKEN_BUDGET="8000",
        HISTORY_KEEP_RECENT="4",
        HISTORY_MAX_MESSAGES="12",
        SUMMARY_MAX_TOKENS="300",
    )
    assert custom.context_token_budget == 8000
    assert custom.history_keep_recent == 4
    assert custom.history_max_messages == 12
    assert custom.summary_max_tokens == 300
