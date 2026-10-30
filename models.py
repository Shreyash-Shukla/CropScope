"""Small data structures shared by the app and data providers."""

from dataclasses import dataclass
from datetime import date, datetime
from math import radians, sin


@dataclass(frozen=True)
class AnalysisArea:
    """A WGS84 rectangle, independent of the saved presentation example."""

    south: float
    west: float
    north: float
    east: float

    @property
    def center(self) -> tuple[float, float]:
        return ((self.south + self.north) / 2, (self.west + self.east) / 2)

    @property
    def area_km2(self) -> float:
        earth_radius_km = 6371.0088
        return (
            earth_radius_km**2
            * radians(self.east - self.west)
            * (sin(radians(self.north)) - sin(radians(self.south)))
        )


@dataclass(frozen=True)
class AnalysisRequest:
    area: AnalysisArea
    crop: str
    growth_stage: str


@dataclass(frozen=True)
class ForecastDay:
    day: date
    rain_mm: float
    max_temp_c: float
    et0_mm: float


@dataclass(frozen=True)
class WeatherResult:
    area: AnalysisArea
    days: tuple[ForecastDay, ...]
    timezone: str
    fetched_at_utc: datetime
    source_url: str


@dataclass(frozen=True)
class SatelliteResult:
    area: AnalysisArea
    scene_id: str
    acquired_at_utc: datetime
    scene_cloud_percent: float
    catalog_url: str
    fetched_at_utc: datetime
    red_preview_png: bytes
    nir_preview_png: bytes
    ndvi_png: bytes | None
    mean_ndvi: float | None
    median_ndvi: float | None
    valid_pixel_percent: float
    quality_message: str | None
    width: int
    height: int
