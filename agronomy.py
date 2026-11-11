"""Agro-climatic water balance and fieldwork suitability indicators."""

from dataclasses import dataclass
from datetime import date

from models import ForecastDay, WeatherResult


COMMON_CROPS: tuple[str, ...] = (
    "Wheat",
    "Rice / Paddy",
    "Corn / Maize",
    "Soybean",
    "Cotton",
    "Barley",
    "Canola / Mustard",
    "Sugarcane",
    "Potato",
)

GROWTH_STAGE_GUIDANCE: dict[str, str] = {
    "Seedling": "Early emergence & root establishment; vulnerable to soil crusting, flooding, and topsoil desiccation.",
    "Vegetative": "Active foliage expansion & canopy closure; critical period for weed scouting and canopy uniformity monitoring.",
    "Flowering": "Peak reproductive & pollination window; highly vulnerable to thermal stress (>35°C) and moisture deficits.",
    "Fruit or grain filling": "Nutrient & carbohydrate translocation; water balance impacts final yield; plan harvest access windows.",
    "Maturity": "Crop dry-down and ripening; track dry weather windows for machinery and harvesting operations.",
    "Other or unknown": "General field scouting and crop observation.",
}


def get_growth_stage_guidance(stage: str | None) -> str:
    """Return operational guidance for a selected growth stage."""
    if not stage:
        return ""
    return GROWTH_STAGE_GUIDANCE.get(stage, "General field scouting and crop observation.")


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


@dataclass(frozen=True)
class OperationalWindows:
    spraying_favorable_days: tuple[date, ...]
    machinery_accessible_days: tuple[date, ...]
    scouting_recommended_days: tuple[date, ...]


def evaluate_operational_windows(weather: WeatherResult) -> OperationalWindows:
    """Identify dedicated operational windows for farm management."""
    spraying = []
    machinery = []
    scouting = []

    for day in weather.days:
        if day.rain_mm < 10.0:
            machinery.append(day.day)
        if day.rain_mm < 2.0 and day.max_temp_c < 32.0:
            spraying.append(day.day)
        if day.rain_mm < 5.0 and day.max_temp_c < 36.0:
            scouting.append(day.day)

    return OperationalWindows(
        spraying_favorable_days=tuple(spraying),
        machinery_accessible_days=tuple(machinery),
        scouting_recommended_days=tuple(scouting),
    )


def summarize_canopy_health(canopy_zones: dict[str, float] | None) -> str:
    """Provide a user-friendly high-level takeaway of the canopy distribution."""
    if not canopy_zones:
        return ""
    values = list(canopy_zones.values())
    if len(values) < 5:
        return ""
    dense, moderate, sparse, bare, water = values[0], values[1], values[2], values[3], values[4]
    active_veg = dense + moderate
    if active_veg >= 70.0:
        return f"🌿 High canopy density: {active_veg:.1f}% of the analysis area displays healthy, active vegetative cover."
    if active_veg >= 40.0:
        return f"🌱 Moderate canopy coverage: {active_veg:.1f}% active vegetation, with {sparse + bare:.1f}% sparse or exposed soil."
    if bare + sparse >= 60.0:
        return f"🍂 Low canopy cover: {bare + sparse:.1f}% of the area is bare soil or early sparse emergence."
    if water >= 20.0:
        return f"💧 Notable moisture / water presence: {water:.1f}% of area indicates standing water or high moisture."
    return f"Canopy distribution: {active_veg:.1f}% active vegetative cover."


@dataclass(frozen=True)
class WeatherAlert:
    level: str  # "danger", "warning", "info", "success"
    category: str
    message: str


def generate_weather_alerts(weather: WeatherResult) -> tuple[WeatherAlert, ...]:
    """Generate high-priority operational and risk alerts for farm management."""
    if not weather.days:
        return ()

    alerts: list[WeatherAlert] = []
    highest_rain = max(weather.days, key=lambda d: d.rain_mm)
    highest_heat = max(weather.days, key=lambda d: d.max_temp_c)
    summary = compute_agro_climatic_summary(weather)
    windows = evaluate_operational_windows(weather)

    # Precipitation alerts
    if highest_rain.rain_mm >= 10.0:
        alerts.append(WeatherAlert(
            level="danger",
            category="Rain",
            message=f"🌧️ Heavy Rain Alert: {highest_rain.rain_mm:.1f} mm forecast on {highest_rain.day.strftime('%a, %d %b')}. High risk of soil runoff and restricted machinery access.",
        ))
    elif highest_rain.rain_mm >= 5.0:
        alerts.append(WeatherAlert(
            level="warning",
            category="Rain",
            message=f"🌦️ Moderate Rain Expected: {highest_rain.rain_mm:.1f} mm forecast on {highest_rain.day.strftime('%a, %d %b')}. May wash off contact chemical applications.",
        ))

    # Thermal alerts
    if highest_heat.max_temp_c >= 38.0:
        alerts.append(WeatherAlert(
            level="danger",
            category="Heat",
            message=f"🔥 Extreme Heat Hazard: Peak {highest_heat.max_temp_c:.1f} °C on {highest_heat.day.strftime('%a, %d %b')}. Severe thermal stress risk; avoid midday spraying and machinery operation.",
        ))
    elif highest_heat.max_temp_c >= 35.0:
        alerts.append(WeatherAlert(
            level="warning",
            category="Heat",
            message=f"☀️ Elevated Temperature Warning: Peak {highest_heat.max_temp_c:.1f} °C on {highest_heat.day.strftime('%a, %d %b')}. High droplet volatilization risk.",
        ))

    # Water balance trends
    if summary.net_balance_mm <= -20.0:
        alerts.append(WeatherAlert(
            level="warning",
            category="Water Balance",
            message=f"⚠️ Atmospheric Moisture Deficit: 7-day cumulative net balance is {summary.net_balance_mm:+.1f} mm. Drying trend indicates increased crop water demand.",
        ))
    elif summary.net_balance_mm >= 25.0:
        alerts.append(WeatherAlert(
            level="info",
            category="Water Balance",
            message=f"💧 Moisture Surplus: 7-day net accumulation of {summary.net_balance_mm:+.1f} mm. Subsoil recharging expected; verify drainage.",
        ))

    # Spray window alerts
    if len(windows.spraying_favorable_days) >= 4:
        alerts.append(WeatherAlert(
            level="success",
            category="Spraying",
            message=f"✨ Favorable Spray Window: {len(windows.spraying_favorable_days)} days forecast with calm conditions and low rain wash-off risk.",
        ))
    elif len(windows.spraying_favorable_days) == 0:
        alerts.append(WeatherAlert(
            level="warning",
            category="Spraying",
            message="⚠️ Limited Spraying Window: Rain or high temperatures restrict chemical applications across the forecast week.",
        ))

    if not alerts:
        alerts.append(WeatherAlert(
            level="success",
            category="General",
            message="🟢 Stable Field Conditions: No severe rainfall or extreme thermal anomalies forecast for the upcoming 7 days.",
        ))

    return tuple(alerts)


