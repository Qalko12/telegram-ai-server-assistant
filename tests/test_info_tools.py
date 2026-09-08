import json
from unittest.mock import AsyncMock, patch
from urllib.error import HTTPError, URLError

import pytest

from ai.tools.info_tools import (
    GetCryptoPricesParams,
    GetExchangeRatesParams,
    GetWeatherParams,
    all_info_tools,
    handle_get_crypto_prices,
    handle_get_exchange_rates,
    handle_get_weather,
)
from ai.tools.registry import ExecutionContext
from security.levels import SecurityLevel


CTX = ExecutionContext(telegram_user_id=42, chat_id=42)


def test_all_info_tools_registered() -> None:
    tools = all_info_tools()
    assert len(tools) == 3
    assert all(t.security_level == SecurityLevel.SAFE for t in tools)
    assert {t.name for t in tools} == {"get_exchange_rates", "get_crypto_prices", "get_weather"}


# --- Exchange Rates ---


def _mock_fetch(data: dict):
    """Мок _fetch_json с заранее заданным ответом."""
    async def fake_fetch(url: str):
        return data
    return fake_fetch


async def test_exchange_rates_usd_to_rub() -> None:
    fake_data = {
        "base": "USD",
        "date": "2025-01-15",
        "rates": {"RUB": 95.5, "EUR": 0.92},
    }
    with patch("ai.tools.info_tools._fetch_json", return_value=fake_data):
        result = await handle_get_exchange_rates(
            GetExchangeRatesParams(base="USD", quote="RUB"), CTX
        )

    assert "USD/RUB: 95.5000" in result
    assert "2025-01-15" in result


async def test_exchange_rates_crypto() -> None:
    # Крипта идёт через CoinGecko, не exchangerate-api
    fake_data = {"bitcoin": {"usd": 50000}}
    with patch("ai.tools.info_tools._fetch_json", return_value=fake_data):
        result = await handle_get_exchange_rates(
            GetExchangeRatesParams(base="BTC", quote="USD"), CTX
        )

    assert "BTC/USD: 50,000.00" in result


async def test_exchange_rates_not_found() -> None:
    fake_data = {"base": "USD", "rates": {"EUR": 0.92}}
    with patch("ai.tools.info_tools._fetch_json", return_value=fake_data):
        result = await handle_get_exchange_rates(
            GetExchangeRatesParams(base="USD", quote="XYZ"), CTX
        )

    assert "Не найден курс" in result
    assert "EUR" in result


async def test_exchange_rates_network_error() -> None:
    with patch("ai.tools.info_tools._fetch_json", side_effect=RuntimeError("HTTP 429")):
        result = await handle_get_exchange_rates(
            GetExchangeRatesParams(base="USD", quote="RUB"), CTX
        )

    assert "Не удалось получить курс" in result
    assert "429" in result


# --- Crypto Prices ---


async def test_crypto_prices() -> None:
    fake_data = {
        "bitcoin": {"usd": 50000, "eur": 46000},
        "ethereum": {"usd": 3000, "eur": 2760},
    }
    with patch("ai.tools.info_tools._fetch_json", return_value=fake_data):
        result = await handle_get_crypto_prices(
            GetCryptoPricesParams(currencies="bitcoin,ethereum", vs_currency="usd"), CTX
        )

    assert "BITCOIN: 50,000.00 USD" in result
    assert "ETHEREUM: 3,000.00 USD" in result


async def test_crypto_prices_unknown_currency() -> None:
    with patch("ai.tools.info_tools._fetch_json", return_value={}):
        result = await handle_get_crypto_prices(
            GetCryptoPricesParams(currencies="unknown-coin", vs_currency="usd"), CTX
        )

    assert "Не найдены данные" in result
    assert "bitcoin, ethereum" in result.lower()


# --- Weather ---


async def test_weather_success() -> None:
    # Мок геокодирования
    geo_data = {"results": [{"name": "Moscow", "latitude": 55.75, "longitude": 37.62}]}
    # Мок погоды
    weather_data = {
        "current": {
            "temperature_2m": 15.5,
            "apparent_temperature": 14.0,
            "relative_humidity_2m": 65,
            "weather_code": 3,
            "wind_speed_10m": 12.5,
        }
    }

    def mock_fetch(url: str):
        if "geocoding-api" in url:
            return geo_data
        return weather_data

    with patch("ai.tools.info_tools._fetch_json", side_effect=mock_fetch):
        result = await handle_get_weather(
            GetWeatherParams(city="Moscow", units="metric"), CTX
        )

    assert "Moscow" in result
    assert "15.5°C" in result
    assert "14.0°C" in result
    assert "65%" in result
    assert "12.5 км/ч" in result
    assert "Пасмурно" in result  # weather_code 3


async def test_weather_city_not_found() -> None:
    with patch("ai.tools.info_tools._fetch_json", return_value={"results": []}):
        result = await handle_get_weather(
            GetWeatherParams(city="Несуществующий-город"), CTX
        )

    assert "не найден" in result.lower()


async def test_weather_imperial_units() -> None:
    geo_data = {"results": [{"name": "London", "latitude": 51.5, "longitude": -0.12}]}
    weather_data = {
        "current": {
            "temperature_2m": 60.0,
            "apparent_temperature": 58.0,
            "relative_humidity_2m": 70,
            "weather_code": 1,
            "wind_speed_10m": 8.0,
        }
    }

    def mock_fetch(url: str):
        if "geocoding-api" in url:
            return geo_data
        return weather_data

    with patch("ai.tools.info_tools._fetch_json", side_effect=mock_fetch):
        result = await handle_get_weather(
            GetWeatherParams(city="London", units="imperial"), CTX
        )

    assert "60.0°F" in result
    assert "8.0 миль/ч" in result


# --- Интеграция в registry ---


def test_info_tools_in_di_registry() -> None:
    from app.di import build_tool_registry

    registry = build_tool_registry()
    tool_names = [t["name"] for t in registry.to_anthropic_tools()]

    assert "get_exchange_rates" in tool_names
    assert "get_crypto_prices" in tool_names
    assert "get_weather" in tool_names
