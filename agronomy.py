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
    suitability: str       # "Favorable", "Caution: Heat", "Caution: Wet", "Caution: Wind", "Caution: Frost", "Restricted: Rain", "Restricted: Heat", "Restricted: Wind"
    reason: str
    min_temp_c: float | None = None
    wind_speed_max_kmh: float | None = None
    rain_probability_pct: float | None = None
    humidity_mean_pct: float | None = None
    gdd_base10: float | None = None


@dataclass(frozen=True)
class AgroClimaticSummary:
    total_rain_mm: float
    total_et0_mm: float
    net_balance_mm: float
    status_label: str
    favorable_days_count: int
    days: tuple[WaterBalanceDay, ...]
    total_gdd_base10: float | None = None
    min_temp_c: float | None = None
    max_wind_kmh: float | None = None
    avg_humidity_pct: float | None = None


def evaluate_fieldwork_suitability(day: ForecastDay) -> tuple[str, str]:
    """Classify fieldwork suitability based on weather thresholds.

    This provides guidance for field accessibility, crop scouting, and spraying operations.
    """
    if day.rain_mm >= 10.0:
        return "Restricted: Rain", f"Forecast rain ({day.rain_mm:.1f} mm) risks runoff, soil compaction, and machinery immobility."
    if day.max_temp_c >= 38.0:
        return "Restricted: Heat", f"Forecast high ({day.max_temp_c:.1f} °C) presents extreme thermal stress and rapid spray evaporation."
    if day.wind_speed_max_kmh is not None and day.wind_speed_max_kmh >= 25.0:
        return "Restricted: Wind", f"High wind ({day.wind_speed_max_kmh:.1f} km/h) causes severe spray drift and lodging risk."
    if day.min_temp_c is not None and day.min_temp_c <= 2.0:
        return "Caution: Frost", f"Near-freezing minimum ({day.min_temp_c:.1f} °C) threatens seedlings and sensitive flowering tissue."
    if day.rain_mm >= 2.0:
        return "Caution: Wet", f"Light to moderate rain ({day.rain_mm:.1f} mm) may wash off chemical applications or dampen access."
    if day.wind_speed_max_kmh is not None and day.wind_speed_max_kmh >= 15.0:
        return "Caution: Wind", f"Breezy wind ({day.wind_speed_max_kmh:.1f} km/h) increases foliar spray drift risk."
    if day.max_temp_c >= 32.0:
        return "Caution: Heat", f"Elevated temperature ({day.max_temp_c:.1f} °C) increases droplet volatilization and plant stress."
    return "Favorable", "Conditions forecast to be favorable for routine field inspection and operations."


def compute_agro_climatic_summary(weather: WeatherResult) -> AgroClimaticSummary:
    """Calculate 7-day cumulative water balance (P - ET0), microclimate stats, and suitability."""
    daily_records: list[WaterBalanceDay] = []
    total_rain = sum(day.rain_mm for day in weather.days)
    total_et0 = sum(day.et0_mm for day in weather.days)
    net_balance = total_rain - total_et0

    favorable_count = 0
    gdd_values: list[float] = []
    min_temps: list[float] = []
    wind_speeds: list[float] = []
    humidities: list[float] = []

    for day in weather.days:
        suitability, reason = evaluate_fieldwork_suitability(day)
        if suitability == "Favorable":
            favorable_count += 1
        gdd = None
        if day.min_temp_c is not None:
            gdd = round(max(0.0, (day.max_temp_c + day.min_temp_c) / 2.0 - 10.0), 1)
            gdd_values.append(gdd)
            min_temps.append(day.min_temp_c)
        if day.wind_speed_max_kmh is not None:
            wind_speeds.append(day.wind_speed_max_kmh)
        if day.humidity_mean_pct is not None:
            humidities.append(day.humidity_mean_pct)
        daily_records.append(WaterBalanceDay(
            day=day.day,
            rain_mm=day.rain_mm,
            max_temp_c=day.max_temp_c,
            et0_mm=day.et0_mm,
            net_balance_mm=round(day.rain_mm - day.et0_mm, 2),
            suitability=suitability,
            reason=reason,
            min_temp_c=day.min_temp_c,
            wind_speed_max_kmh=day.wind_speed_max_kmh,
            rain_probability_pct=day.rain_probability_pct,
            humidity_mean_pct=day.humidity_mean_pct,
            gdd_base10=gdd,
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
        total_gdd_base10=round(sum(gdd_values), 1) if gdd_values else None,
        min_temp_c=round(min(min_temps), 1) if min_temps else None,
        max_wind_kmh=round(max(wind_speeds), 1) if wind_speeds else None,
        avg_humidity_pct=round(sum(humidities) / len(humidities), 1) if humidities else None,
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
        wind_ok = day.wind_speed_max_kmh is None or day.wind_speed_max_kmh < 15.0
        if day.rain_mm < 2.0 and day.max_temp_c < 32.0 and wind_ok:
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

    # Frost / Cold-wave alerts
    cold_days = [d for d in weather.days if d.min_temp_c is not None]
    if cold_days:
        coldest = min(cold_days, key=lambda d: d.min_temp_c)  # type: ignore[arg-type]
        if coldest.min_temp_c is not None and coldest.min_temp_c <= 2.0:
            alerts.append(WeatherAlert(
                level="danger",
                category="Frost",
                message=f"❄️ Frost Hazard: Minimum temperature forecast at {coldest.min_temp_c:.1f} °C on {coldest.day.strftime('%a, %d %b')}. Protect sensitive seedlings and tender crops.",
            ))
        elif coldest.min_temp_c is not None and coldest.min_temp_c <= 5.0:
            alerts.append(WeatherAlert(
                level="warning",
                category="Frost",
                message=f"🌡️ Cold Night Advisory: Forecast low of {coldest.min_temp_c:.1f} °C on {coldest.day.strftime('%a, %d %b')}. Monitor cold-sensitive vegetables and young plants.",
            ))

    # Wind / Spray drift alerts
    windy_days = [d for d in weather.days if d.wind_speed_max_kmh is not None]
    if windy_days:
        windiest = max(windy_days, key=lambda d: d.wind_speed_max_kmh)  # type: ignore[arg-type]
        if windiest.wind_speed_max_kmh is not None and windiest.wind_speed_max_kmh >= 25.0:
            alerts.append(WeatherAlert(
                level="warning",
                category="Wind",
                message=f"💨 High Wind Alert: Winds up to {windiest.wind_speed_max_kmh:.1f} km/h on {windiest.day.strftime('%a, %d %b')}. Avoid spraying due to severe chemical drift risk.",
            ))
        elif windiest.wind_speed_max_kmh is not None and windiest.wind_speed_max_kmh >= 15.0:
            alerts.append(WeatherAlert(
                level="info",
                category="Wind",
                message=f"🌬️ Moderate Spray Drift Risk: Winds up to {windiest.wind_speed_max_kmh:.1f} km/h on {windiest.day.strftime('%a, %d %b')}. Prefer calm early-morning spray windows.",
            ))

    # Warm-humid fungal scouting alert
    humid_warm_days = sum(
        1
        for d in weather.days
        if d.humidity_mean_pct is not None and d.humidity_mean_pct >= 80.0 and d.max_temp_c >= 18.0
    )
    if humid_warm_days >= 3:
        alerts.append(WeatherAlert(
            level="info",
            category="Humidity",
            message=f"🍄 Humid Microclimate Watch: {humid_warm_days} days forecast with ≥80% mean humidity. Inspect lower canopy leaves for early fungal spots (scouting cue, not a diagnosis).",
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


