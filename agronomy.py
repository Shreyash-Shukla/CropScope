"""Agro-climatic water balance and fieldwork suitability indicators."""

from dataclasses import dataclass
from datetime import date

from models import ForecastDay, WeatherResult


@dataclass(frozen=True)
class WaterBalanceDay:
    day: date
    rain_mm: float
    max_temp_c: float
    et0_mm: float
    net_balance_mm: float  # rain - et0
    suitability: str       # "Favorable", "Caution: Heat", "Caution: Wet", "Restricted: Rain", "Restricted: Heat"
    reason: str


@dataclass(frozen=True)
class AgroClimaticSummary:
    total_rain_mm: float
    total_et0_mm: float
    net_balance_mm: float
    status_label: str
    favorable_days_count: int
    days: tuple[WaterBalanceDay, ...]


def evaluate_fieldwork_suitability(day: ForecastDay) -> tuple[str, str]:
    """Classify fieldwork suitability based on weather thresholds.

    This provides guidance for field accessibility, crop scouting, and spraying operations.
    """
    if day.rain_mm >= 10.0:
        return "Restricted: Rain", f"Forecast rain ({day.rain_mm:.1f} mm) risks runoff, soil compaction, and machinery immobility."
    if day.max_temp_c >= 38.0:
        return "Restricted: Heat", f"Forecast high ({day.max_temp_c:.1f} °C) presents extreme thermal stress and rapid spray evaporation."
    if day.rain_mm >= 2.0:
        return "Caution: Wet", f"Light to moderate rain ({day.rain_mm:.1f} mm) may wash off chemical applications or dampen access."
    if day.max_temp_c >= 32.0:
        return "Caution: Heat", f"Elevated temperature ({day.max_temp_c:.1f} °C) increases droplet volatilization and plant stress."
    return "Favorable", "Conditions forecast to be favorable for routine field inspection and operations."


def compute_agro_climatic_summary(weather: WeatherResult) -> AgroClimaticSummary:
    """Calculate 7-day cumulative water balance (P - ET0) and suitability."""
    daily_records: list[WaterBalanceDay] = []
    total_rain = sum(day.rain_mm for day in weather.days)
    total_et0 = sum(day.et0_mm for day in weather.days)
    net_balance = total_rain - total_et0

    favorable_count = 0
    for day in weather.days:
        suitability, reason = evaluate_fieldwork_suitability(day)
        if suitability == "Favorable":
            favorable_count += 1
        daily_records.append(WaterBalanceDay(
            day=day.day,
            rain_mm=day.rain_mm,
            max_temp_c=day.max_temp_c,
            et0_mm=day.et0_mm,
            net_balance_mm=round(day.rain_mm - day.et0_mm, 2),
            suitability=suitability,
            reason=reason,
        ))

    if net_balance <= -15.0:
        status = "Net Atmospheric Deficit (Drying Trend)"
    elif net_balance >= 15.0:
        status = "Net Atmospheric Surplus (Moisture Accumulation)"
    else:
        status = "Near-Neutral Atmospheric Balance"

    return AgroClimaticSummary(
        total_rain_mm=round(total_rain, 2),
        total_et0_mm=round(total_et0, 2),
        net_balance_mm=round(net_balance, 2),
        status_label=status,
        favorable_days_count=favorable_count,
        days=tuple(daily_records),
    )
