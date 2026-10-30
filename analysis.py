"""Independent source outcomes and recommendation fallback for one request."""

from dataclasses import dataclass
from typing import Callable

from ai import AIError, rank_with_gemini
from cache import CacheStore
from models import AnalysisRequest, SatelliteResult, WeatherResult
from recommendations import Suggestion, build_candidates, rule_based_suggestions
from satellite import SatelliteError, fetch_satellite
from weather import WeatherError, fetch_weather


@dataclass(frozen=True)
class SourceState:
    result: WeatherResult | SatelliteResult | None
    cached: bool
    error: str | None


@dataclass(frozen=True)
class AnalysisOutcome:
    request: AnalysisRequest
    weather: SourceState
    satellite: SourceState
    suggestions: tuple[Suggestion, ...]
    suggestion_source: str | None


def _fetch_source(area, fetcher, loader, saver, error_type, *, cached_only: bool) -> SourceState:
    if cached_only:
        cached = loader(area)
        return SourceState(cached, cached is not None,
                           None if cached is not None else "No saved result exists for this exact rectangle.")
    try:
        result = fetcher(area)
        try:
            saver(result)
        except OSError:
            pass  # Live data remains usable even if local storage is unavailable.
        return SourceState(result, False, None)
    except error_type as exc:
        cached = loader(area)
        return SourceState(cached, cached is not None, str(exc))


def analyze(
    request: AnalysisRequest,
    cache: CacheStore,
    *,
    cached_only: bool = False,
    on_weather: Callable[[SourceState], None] | None = None,
    on_satellite: Callable[[SourceState], None] | None = None,
    weather_fetcher=fetch_weather,
    satellite_fetcher=fetch_satellite,
    ai_ranker=rank_with_gemini,
) -> AnalysisOutcome:
    """Never borrow another rectangle's data or cite an unavailable source."""
    weather = _fetch_source(request.area, weather_fetcher, cache.load_weather,
                            cache.save_weather, WeatherError, cached_only=cached_only)
    if on_weather:
        on_weather(weather)
    satellite = _fetch_source(request.area, satellite_fetcher, cache.load_satellite,
                              cache.save_satellite, SatelliteError, cached_only=cached_only)
    if on_satellite:
        on_satellite(satellite)
    weather_result = weather.result if isinstance(weather.result, WeatherResult) else None
    satellite_result = satellite.result if isinstance(satellite.result, SatelliteResult) else None
    evidence, candidates = build_candidates(request, weather_result, satellite_result)
    if not candidates:
        return AnalysisOutcome(request, weather, satellite, (), None)
    try:
        suggestions = ai_ranker(request, evidence, candidates)
        source = "Gemini-ranked, evidence-checked"
    except AIError:
        suggestions = rule_based_suggestions(evidence, candidates)
        source = "Rule-based fallback (Gemini unavailable or response rejected)"
    return AnalysisOutcome(request, weather, satellite, suggestions, source)
