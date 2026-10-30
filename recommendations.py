"""Finite, inspectable management checks grounded in available observations."""

from dataclasses import dataclass

from models import AnalysisRequest, SatelliteResult, WeatherResult


@dataclass(frozen=True)
class Evidence:
    id: str
    text: str


@dataclass(frozen=True)
class Candidate:
    id: str
    title: str
    action: str
    evidence_ids: tuple[str, ...]
    priority: int


@dataclass(frozen=True)
class Suggestion:
    candidate: Candidate
    evidence: tuple[Evidence, ...]


def build_candidates(
    request: AnalysisRequest,
    weather: WeatherResult | None,
    satellite: SatelliteResult | None,
) -> tuple[tuple[Evidence, ...], tuple[Candidate, ...]]:
    """Propose only actions supported by a present, area-matched source."""
    evidence: list[Evidence] = []
    candidates: list[Candidate] = []
    if weather is not None and weather.area == request.area:
        total_rain = sum(day.rain_mm for day in weather.days)
        highest_rain = max(weather.days, key=lambda day: day.rain_mm)
        highest_heat = max(weather.days, key=lambda day: day.max_temp_c)
        total_et0 = sum(day.et0_mm for day in weather.days)
        evidence.extend((
            Evidence("rain_total", f"Seven-day forecast rain: {total_rain:.1f} mm ({weather.days[0].day} to {weather.days[-1].day})."),
            Evidence("rain_peak", f"Highest forecast daily rain: {highest_rain.rain_mm:.1f} mm on {highest_rain.day}."),
            Evidence("heat_peak", f"Highest forecast daily maximum: {highest_heat.max_temp_c:.1f} °C on {highest_heat.day}."),
            Evidence("et0_total", f"Seven-day reference ET₀ total: {total_et0:.1f} mm."),
        ))
        if highest_rain.rain_mm >= 10:
            candidates.append(Candidate(
                "check_drainage", "Check drainage before heavy forecast rain",
                "Inspect field drainage and access before the forecast rain; confirm conditions on site.",
                ("rain_peak",), 10,
            ))
        if highest_heat.max_temp_c >= 35:
            candidates.append(Candidate(
                "check_heat", "Check for heat stress",
                "Inspect the crop during the hotter forecast days and check local conditions.",
                ("heat_peak",), 20,
            ))
        if total_rain <= 5 and total_et0 >= 15:
            candidates.append(Candidate(
                "check_soil", "Check soil moisture on site",
                "Check soil moisture before making any irrigation decision; this forecast is not a soil measurement.",
                ("rain_total", "et0_total"), 30,
            ))
        candidates.append(Candidate(
            "review_forecast", "Review the forecast before field work",
            "Use the dated forecast to plan a field visit and recheck it as conditions change.",
            ("rain_total", "heat_peak"), 80,
        ))

    if satellite is not None and satellite.area == request.area and satellite.mean_ndvi is not None:
        evidence.extend((
            Evidence("ndvi_mean", f"Mean NDVI: {satellite.mean_ndvi:.3f} from scene {satellite.scene_id} acquired {satellite.acquired_at_utc.date()}."),
            Evidence("valid_pixels", f"Usable pixels in the selected rectangle: {satellite.valid_pixel_percent:.1f}%."),
        ))
        if satellite.mean_ndvi < 0.35:
            candidates.append(Candidate(
                "inspect_greenness", "Inspect low-greenness patches",
                "Compare the NDVI image with the crop and growth stage on site; bare soil or other land can affect the rectangle.",
                ("ndvi_mean", "valid_pixels"), 40,
            ))
        candidates.append(Candidate(
            "verify_imagery", "Compare imagery with the field",
            "Check whether the dated image reflects current field conditions before acting on it.",
            ("ndvi_mean", "valid_pixels"), 90,
        ))
    return tuple(evidence), tuple(sorted(candidates, key=lambda item: item.priority))


def rule_based_suggestions(
    evidence: tuple[Evidence, ...], candidates: tuple[Candidate, ...], limit: int = 3,
) -> tuple[Suggestion, ...]:
    by_id = {item.id: item for item in evidence}
    return tuple(
        Suggestion(candidate, tuple(by_id[item_id] for item_id in candidate.evidence_ids))
        for candidate in candidates[:limit]
    )
