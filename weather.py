"""Fetch and validate a seven-day Open-Meteo forecast."""

import json
import math
from datetime import date, datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from models import AnalysisArea, ForecastDay, WeatherResult


API_URL = "https://api.open-meteo.com/v1/forecast"
DAILY_FIELDS = (
    "rain_sum",
    "temperature_2m_max",
    "et0_fao_evapotranspiration",
)


class WeatherError(Exception):
    """A forecast could not be fetched or safely displayed."""


def _number(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise WeatherError(f"The forecast has a missing or invalid {name} value.")
    number = float(value)
    if not math.isfinite(number):
        raise WeatherError(f"The forecast has a non-finite {name} value.")
    return number


def parse_weather(
    payload: dict,
    area: AnalysisArea,
    source_url: str,
    fetched_at_utc: datetime,
) -> WeatherResult:
    """Reject incomplete data instead of displaying partial or misleading rows."""
    try:
        daily = payload["daily"]
        units = payload["daily_units"]
        timezone_name = payload["timezone"]
        dates = daily["time"]
        rain = daily["rain_sum"]
        temperatures = daily["temperature_2m_max"]
        et0 = daily["et0_fao_evapotranspiration"]
    except (KeyError, TypeError) as exc:
        raise WeatherError("The weather service returned an incomplete forecast.") from exc

    if (
        not isinstance(units, dict)
        or not isinstance(timezone_name, str)
        or not timezone_name
        or not all(isinstance(values, list) and len(values) == 7 for values in (dates, rain, temperatures, et0))
    ):
        raise WeatherError("The weather service did not return seven complete days.")

    expected_units = {
        "rain_sum": "mm",
        "temperature_2m_max": "°C",
        "et0_fao_evapotranspiration": "mm",
    }
    if any(units.get(key) != unit for key, unit in expected_units.items()):
        raise WeatherError("The weather service returned unexpected measurement units.")

    try:
        rows = tuple(
            ForecastDay(
                day=date.fromisoformat(dates[index]),
                rain_mm=_number(rain[index], "rain"),
                max_temp_c=_number(temperatures[index], "temperature"),
                et0_mm=_number(et0[index], "ET₀"),
            )
            for index in range(7)
        )
    except (TypeError, ValueError) as exc:
        raise WeatherError("The weather service returned an invalid forecast date.") from exc

    if any((rows[index + 1].day - rows[index].day).days != 1 for index in range(6)):
        raise WeatherError("The forecast dates are not seven consecutive days.")
    if any(row.rain_mm < 0 or row.et0_mm < 0 for row in rows):
        raise WeatherError("The forecast contains a negative rain or ET₀ value.")

    return WeatherResult(area, rows, timezone_name, fetched_at_utc, source_url)


def fetch_weather(area: AnalysisArea) -> WeatherResult:
    latitude, longitude = area.center

    query = urlencode(
        {
            "latitude": latitude,
            "longitude": longitude,
            "daily": ",".join(DAILY_FIELDS),
            "timezone": "auto",
            "forecast_days": 7,
        }
    )
    url = f"{API_URL}?{query}"
    request = Request(url, headers={"User-Agent": "CropScope/0.1 (student weather demo)"})
    try:
        with urlopen(request, timeout=20) as response:
            payload = json.load(response)
    except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        raise WeatherError("Could not reach Open-Meteo. Check the connection and try again.") from exc

    if not isinstance(payload, dict) or payload.get("error"):
        raise WeatherError("Open-Meteo could not provide a forecast for this area.")

    return parse_weather(payload, area, url, datetime.now(timezone.utc))
