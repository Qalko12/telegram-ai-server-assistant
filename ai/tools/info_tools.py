"""AI-инструменты для получения информации из интернета: курсы валют, крипта, погода.

Это специализированные инструменты для частых запросов. Общий web_search уже есть
в web_tools.py (через Tavily), но для курсов валют и погоды лучше использовать
прямые API — они быстрее и точнее.

Все данные из интернета считаются НЕДОВЕРЕННЫМИ (ТЗ §38) — Claude оборачивает их
в <untrusted_tool_output> в agent_loop автоматически.
"""

import json
import logging
import urllib.error
import urllib.request
from typing import Literal

from pydantic import BaseModel, Field

from ai.tools.registry import ExecutionContext, ToolSpec
from app.config import settings
from security.levels import SecurityLevel

logger = logging.getLogger(__name__)

HTTP_TIMEOUT_SECONDS = 15


class _NoParams(BaseModel):
    pass


class GetExchangeRatesParams(BaseModel):
    base: str = Field(default="USD", description="Базовая валюта (USD, EUR, RUB, BTC и т.д.)")
    quote: str = Field(default="RUB", description="Целевая валюта (RUB, USD, EUR и т.д.)")


class GetCryptoPricesParams(BaseModel):
    currencies: str = Field(
        default="bitcoin,ethereum",
        description="Криптовалюты через запятую (bitcoin, ethereum, toncoin и т.д. — id из CoinGecko)"
    )
    vs_currency: str = Field(default="usd", description="Валюта для цены (usd, eur, rub)")


class GetWeatherParams(BaseModel):
    city: str = Field(description="Город (Moscow, London, Paris и т.д.)")
    units: Literal["metric", "imperial"] = Field(default="metric", description="Метрическая (°C) или имперская (°F)")


def _fetch_json(url: str) -> dict:
    """GET запрос с таймаутом. Возвращает распарсенный JSON или бросает исключение."""
    request = urllib.request.Request(url, headers={"User-Agent": "AliceBot/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.code}: {exc.reason}") from exc
    except (urllib.error.URLError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Ошибка запроса: {exc}") from exc


async def handle_get_exchange_rates(params: GetExchangeRatesParams, ctx: ExecutionContext) -> str:
    """Курсы фиатных валют через exchangerate-api.com (бесплатно, без ключа)."""
    base = params.base.upper()
    quote = params.quote.upper()

    # Пробуем крипту через CoinGecko, если base или quote — крипта
    if base in {"BTC", "ETH", "TON", "BNB", "SOL", "XRP"} or quote in {"BTC", "ETH", "TON", "BNB", "SOL", "XRP"}:
        return await _get_crypto_rate(base, quote)

    # Фиатные валюты через exchangerate-api.com
    url = f"https://api.exchangerate-api.com/v4/latest/{base}"
    try:
        data = _fetch_json(url)
    except RuntimeError as exc:
        return f"Не удалось получить курс {base}: {exc}"

    rates = data.get("rates", {})
    rate = rates.get(quote)
    if rate is None:
        return f"Не найден курс {base} → {quote}. Доступные: {', '.join(list(rates.keys())[:10])}..."

    return (
        f"Курс {base}/{quote}: {rate:.4f}\n"
        f"Дата обновления: {data.get('date', 'неизвестно')}"
    )


async def _get_crypto_rate(base: str, quote: str) -> str:
    """Курс крипты к фиату или другой крипте через CoinGecko."""
    # Маппинг тикеров → id CoinGecko
    ticker_to_id = {
        "BTC": "bitcoin", "ETH": "ethereum", "TON": "toncoin",
        "BNB": "binancecoin", "SOL": "solana", "XRP": "ripple",
    }

    base_id = ticker_to_id.get(base)
    quote_id = ticker_to_id.get(quote)

    if base_id and quote.lower() in {"usd", "eur", "rub"}:
        # Крипта → фиат
        url = f"https://api.coingecko.com/api/v3/simple/price?ids={base_id}&vs_currencies={quote.lower()}"
        try:
            data = _fetch_json(url)
            price = data[base_id][quote.lower()]
            return f"Курс {base}/{quote}: {price:,.2f}"
        except (RuntimeError, KeyError) as exc:
            return f"Не удалось получить курс {base}: {exc}"

    if base_id and quote_id:
        # Крипта → крипта
        url = f"https://api.coingecko.com/api/v3/simple/price?ids={base_id}&vs_currencies={quote_id}"
        try:
            data = _fetch_json(url)
            price = data[base_id][quote_id]
            return f"Курс {base}/{quote}: {price:.6f}"
        except (RuntimeError, KeyError) as exc:
            return f"Не удалось получить курс {base}/{quote}: {exc}"

    return f"Неподдерживаемая пара {base}/{quote}. Для фиата используй get_exchange_rates, для крипты — get_crypto_prices."


async def handle_get_crypto_prices(params: GetCryptoPricesParams, ctx: ExecutionContext) -> str:
    """Цены криптовалют через CoinGecko (бесплатно, без ключа)."""
    currencies = params.currencies.lower().replace(" ", "")
    vs = params.vs_currency.lower()

    url = f"https://api.coingecko.com/api/v3/simple/price?ids={currencies}&vs_currencies={vs}"
    try:
        data = _fetch_json(url)
    except RuntimeError as exc:
        return f"Не удалось получить цены криптовалют: {exc}"

    if not data:
        return f"Не найдены данные для: {params.currencies}. Проверь id (bitcoin, ethereum, toncoin и т.д.)"

    lines = []
    for currency, prices in data.items():
        price = prices.get(vs)
        if price is not None:
            lines.append(f"• {currency.upper()}: {price:,.2f} {vs.upper()}")

    return "Криптовалюты:\n" + "\n".join(lines) if lines else "Нет данных."


async def handle_get_weather(params: GetWeatherParams, ctx: ExecutionContext) -> str:
    """Погода через Open-Meteo (бесплатно, без ключа)."""
    # Сначала геокодируем город
    geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={params.city}&count=1&language=ru&format=json"
    try:
        geo_data = _fetch_json(geo_url)
    except RuntimeError as exc:
        return f"Не удалось найти город {params.city}: {exc}"

    results = geo_data.get("results", [])
    if not results:
        return f"Город не найден: {params.city}"

    location = results[0]
    lat = location["latitude"]
    lon = location["longitude"]
    city_name = location.get("name", params.city)

    # Теперь погода
    units = "metric" if params.units == "metric" else "imperial"
    weather_url = (
        f"https://api.open-meteo.com/v1/forecast?"
        f"latitude={lat}&longitude={lon}"
        f"&current=temperature_2m,relative_humidity_2m,apparent_temperature,precipitation,weather_code,wind_speed_10m"
        f"&temperature_unit={'celsius' if units == 'metric' else 'fahrenheit'}"
        f"&wind_speed_unit={'kmh' if units == 'metric' else 'mph'}"
        f"&timezone=auto"
    )

    try:
        weather_data = _fetch_json(weather_url)
    except RuntimeError as exc:
        return f"Не удалось получить погоду для {city_name}: {exc}"

    current = weather_data.get("current", {})
    temp = current.get("temperature_2m")
    feels = current.get("apparent_temperature")
    humidity = current.get("relative_humidity_2m")
    wind = current.get("wind_speed_10m")

    # Коды погоды WMO
    weather_code = current.get("weather_code", 0)
    weather_desc = _wmo_code_to_text(weather_code)

    unit_temp = "°C" if units == "metric" else "°F"
    unit_wind = "км/ч" if units == "metric" else "миль/ч"

    return (
        f"Погода в {city_name}:\n"
        f"🌡 Температура: {temp}{unit_temp} (ощущается как {feels}{unit_temp})\n"
        f"☁️ {weather_desc}\n"
        f"💧 Влажность: {humidity}%\n"
        f"💨 Ветер: {wind} {unit_wind}"
    )


def _wmo_code_to_text(code: int) -> str:
    """Коды погоды WMO → текст."""
    codes = {
        0: "Ясно",
        1: "Преимущественно ясно", 2: "Переменная облачность", 3: "Пасмурно",
        45: "Туман", 48: "Изморозь",
        51: "Морось", 53: "Морось", 55: "Морось",
        61: "Небольшой дождь", 63: "Дождь", 65: "Сильный дождь",
        71: "Небольшой снег", 73: "Снег", 75: "Сильный снег",
        77: "Снежная крупа",
        80: "Ливень", 81: "Ливень", 82: "Сильный ливень",
        85: "Снегопад", 86: "Снегопад",
        95: "Гроза", 96: "Гроза с градом", 99: "Гроза с градом",
    }
    return codes.get(code, f"Код погоды: {code}")


GET_EXCHANGE_RATES = ToolSpec(
    name="get_exchange_rates",
    description=(
        "Получить курс валюты (USD, EUR, RUB и т.д.) или криптовалюты (BTC, ETH, TON и т.д.). "
        "Пример: get_exchange_rates(base='USD', quote='RUB') → курс доллара к рублю."
    ),
    input_model=GetExchangeRatesParams,
    handler=handle_get_exchange_rates,
    security_level=SecurityLevel.SAFE,
)

GET_CRYPTO_PRICES = ToolSpec(
    name="get_crypto_prices",
    description=(
        "Получить цены криптовалют (Bitcoin, Ethereum, TON и т.д.) через CoinGecko. "
        "Пример: get_crypto_prices(currencies='bitcoin,ethereum', vs_currency='usd')"
    ),
    input_model=GetCryptoPricesParams,
    handler=handle_get_crypto_prices,
    security_level=SecurityLevel.SAFE,
)

GET_WEATHER = ToolSpec(
    name="get_weather",
    description="Получить текущую погоду в городе (температура, влажность, ветер, описание).",
    input_model=GetWeatherParams,
    handler=handle_get_weather,
    security_level=SecurityLevel.SAFE,
)


def all_info_tools() -> tuple[ToolSpec, ...]:
    return (GET_EXCHANGE_RATES, GET_CRYPTO_PRICES, GET_WEATHER)
