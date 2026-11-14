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

    @property
    def area_ha(self) -> float:
        """Area in hectares (1 km² = 100 ha)."""
        return self.area_km2 * 100.0

    @property
    def area_acres(self) -> float:
        """Area in acres (1 ha ≈ 2.47105 ac)."""
        return self.area_km2 * 247.10538

    def formatted_area(self) -> str:
        """User-friendly multi-unit representation: ha, acres, and km²."""
        return f"{self.area_ha:.2f} ha ({self.area_acres:.2f} ac / {self.area_km2:.3f} km²)"


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
    mean_savi: float | None = None
    canopy_zones: dict[str, float] | None = None
    true_color_png: bytes | None = None
    scene_thumbnail_png: bytes | None = None
    scene_thumbnail_url: str | None = None
    platform: str | None = None
    sun_elevation: float | None = None
    sun_azimuth: float | None = None
    mgrs_tile: str | None = None

    def __getattr__(self, name: str):
        # Gracefully return None for optional fields on legacy or unpickled instances
        return None
