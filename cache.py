"""Dated JSON/PNG cache keyed by the exact selected rectangle."""

import base64
import hashlib
import json
from dataclasses import asdict
from datetime import date, datetime
from pathlib import Path

from models import AnalysisArea, ForecastDay, SatelliteResult, WeatherResult


VERSION = 1


def _area_dict(area: AnalysisArea) -> dict:
    return asdict(area)


def _name(kind: str, area: AnalysisArea) -> str:
    key = json.dumps(_area_dict(area), sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:20]
    return f"{kind}_{digest}.json"


class CacheStore:
    def __init__(self, root: Path, sample_root: Path | None = None):
        self.root = root
        self.sample_root = sample_root

    def _read(self, kind: str, area: AnalysisArea) -> dict | None:
        filename = _name(kind, area)
        for directory in (self.root, self.sample_root):
            if directory is None:
                continue
            try:
                payload = json.loads((directory / filename).read_text(encoding="utf-8"))
                if payload.get("version") == VERSION and payload.get("area") == _area_dict(area):
                    return payload
            except (OSError, ValueError, TypeError, AttributeError):
                continue
        return None

    def _write(self, kind: str, area: AnalysisArea, payload: dict) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / _name(kind, area)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
        temporary.replace(path)

    def save_weather(self, result: WeatherResult) -> None:
        self._write("weather", result.area, {
            "version": VERSION, "area": _area_dict(result.area),
            "fetched_at_utc": result.fetched_at_utc.isoformat(),
            "timezone": result.timezone, "source_url": result.source_url,
            "days": [{"day": row.day.isoformat(), "rain_mm": row.rain_mm,
                      "max_temp_c": row.max_temp_c, "et0_mm": row.et0_mm}
                     for row in result.days],
        })

    def load_weather(self, area: AnalysisArea) -> WeatherResult | None:
        payload = self._read("weather", area)
        if payload is None:
            return None
        try:
            days = tuple(ForecastDay(date.fromisoformat(row["day"]),
                                     float(row["rain_mm"]), float(row["max_temp_c"]),
                                     float(row["et0_mm"])) for row in payload["days"])
            if len(days) != 7:
                return None
            return WeatherResult(area, days, payload["timezone"],
                                 datetime.fromisoformat(payload["fetched_at_utc"]),
                                 payload["source_url"])
        except (KeyError, TypeError, ValueError):
            return None

    def save_satellite(self, result: SatelliteResult) -> None:
        encode = lambda data: base64.b64encode(data).decode("ascii") if data is not None else None
        self._write("satellite", result.area, {
            "version": VERSION, "area": _area_dict(result.area),
            "scene_id": result.scene_id,
            "acquired_at_utc": result.acquired_at_utc.isoformat(),
            "scene_cloud_percent": result.scene_cloud_percent,
            "catalog_url": result.catalog_url,
            "fetched_at_utc": result.fetched_at_utc.isoformat(),
            "red_preview_png": encode(result.red_preview_png),
            "nir_preview_png": encode(result.nir_preview_png),
            "ndvi_png": encode(result.ndvi_png),
            "mean_ndvi": result.mean_ndvi, "median_ndvi": result.median_ndvi,
            "valid_pixel_percent": result.valid_pixel_percent,
            "quality_message": result.quality_message,
            "width": result.width, "height": result.height,
        })

    def load_satellite(self, area: AnalysisArea) -> SatelliteResult | None:
        payload = self._read("satellite", area)
        if payload is None:
            return None
        try:
            decode = lambda value: base64.b64decode(value, validate=True) if value is not None else None
            return SatelliteResult(
                area=area, scene_id=payload["scene_id"],
                acquired_at_utc=datetime.fromisoformat(payload["acquired_at_utc"]),
                scene_cloud_percent=float(payload["scene_cloud_percent"]),
                catalog_url=payload["catalog_url"],
                fetched_at_utc=datetime.fromisoformat(payload["fetched_at_utc"]),
                red_preview_png=decode(payload["red_preview_png"]),
                nir_preview_png=decode(payload["nir_preview_png"]),
                ndvi_png=decode(payload["ndvi_png"]),
                mean_ndvi=float(payload["mean_ndvi"]) if payload["mean_ndvi"] is not None else None,
                median_ndvi=float(payload["median_ndvi"]) if payload["median_ndvi"] is not None else None,
                valid_pixel_percent=float(payload["valid_pixel_percent"]),
                quality_message=payload["quality_message"],
                width=int(payload["width"]), height=int(payload["height"]),
            )
        except (KeyError, TypeError, ValueError):
            return None
