"""Read selected-area Sentinel-2 bands and calculate cloud-masked NDVI."""

import io
import json
import math
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import numpy as np
import rasterio
from PIL import Image
from rasterio.errors import RasterioError
from rasterio.enums import Resampling
from rasterio.vrt import WarpedVRT
from rasterio.warp import transform_bounds
from rasterio.windows import from_bounds

from models import AnalysisArea, SatelliteResult


SEARCH_URL = "https://earth-search.aws.element84.com/v1/search"
COLLECTION = "sentinel-2-c1-l2a"
LOOKBACK_DAYS = 35
MAX_SCENE_CLOUD_PERCENT = 60.0
MAX_CANDIDATES = 4
SATELLITE_BUDGET_SECONDS = 90
MIN_VALID_PIXEL_PERCENT = 10.0
# SCL: vegetation, bare soil, water. All remaining classes are uncertain,
# shadows, clouds, snow, saturated/defective, or no data.
CLEAR_SCL_CLASSES = (4, 5, 6)


class SatelliteError(Exception):
    """Satellite metadata or pixels could not be retrieved safely."""


class NoSceneError(SatelliteError):
    """No usable recent scene was found for this rectangle."""


@dataclass(frozen=True)
class BandWindow:
    pixels: np.ma.MaskedArray
    transform: rasterio.Affine
    crs: rasterio.crs.CRS


def search_scenes(area: AnalysisArea, *, now: datetime | None = None) -> list[dict]:
    """Search the whole rectangle, then rank recent scenes by cloud and age."""
    now = now or datetime.now(timezone.utc)
    start = now - timedelta(days=LOOKBACK_DAYS)
    body = {
        "collections": [COLLECTION],
        "bbox": [area.west, area.south, area.east, area.north],
        "datetime": f"{start:%Y-%m-%dT%H:%M:%SZ}/{now:%Y-%m-%dT%H:%M:%SZ}",
        "limit": 100,
        "sortby": [{"field": "properties.datetime", "direction": "desc"}],
    }
    request = Request(
        SEARCH_URL,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "User-Agent": "CropScope/0.2 (student satellite demo)"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=20) as response:
            payload = json.load(response)
    except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
        raise SatelliteError("Could not search Sentinel-2 scenes. Try again later.") from exc

    if not isinstance(payload, dict) or not isinstance(payload.get("features"), list):
        raise SatelliteError("The satellite catalog returned an invalid scene list.")

    candidates = []
    for item in payload["features"]:
        try:
            if item["collection"] != COLLECTION:
                continue
            if not isinstance(item["id"], str) or not item["id"]:
                continue
            acquired = datetime.fromisoformat(item["properties"]["datetime"].replace("Z", "+00:00"))
            cloud = float(item["properties"]["eo:cloud_cover"])
            assets = item["assets"]
            if not all(isinstance(assets[band]["href"], str) and assets[band]["href"].startswith("https://") for band in ("red", "nir", "scl")):
                continue
            _reflectance_scale_offset(assets["red"])
            _reflectance_scale_offset(assets["nir"])
            if not (acquired.tzinfo and start <= acquired <= now and math.isfinite(cloud) and 0 <= cloud <= MAX_SCENE_CLOUD_PERCENT):
                continue
            candidates.append(item)
        except (KeyError, TypeError, ValueError, OverflowError, SatelliteError):
            continue

    candidates.sort(key=lambda item: (
        float(item["properties"]["eo:cloud_cover"]) +
        (now - datetime.fromisoformat(item["properties"]["datetime"].replace("Z", "+00:00"))).total_seconds() / 86400 * 0.4,
        item["id"],
    ))
    return candidates[:MAX_CANDIDATES]


def _reflectance_scale_offset(asset: dict) -> tuple[float, float]:
    """Use the STAC asset's radiometric conversion; never guess the offset."""
    try:
        band = asset["raster:bands"][0]
        scale, offset = float(band["scale"]), float(band["offset"])
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise SatelliteError("A scene is missing red or NIR reflectance scale/offset metadata.") from exc
    if not (math.isfinite(scale) and scale > 0 and math.isfinite(offset)):
        raise SatelliteError("A scene has invalid reflectance scale/offset metadata.")
    return scale, offset


def _read_band(href: str, area: AnalysisArea) -> BandWindow:
    """Read a bounded native-resolution COG window; reject partial tile coverage."""
    with rasterio.Env(
        GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR",
        GDAL_HTTP_TIMEOUT="15",
        GDAL_HTTP_MAX_RETRY="1",
        AWS_NO_SIGN_REQUEST="YES",
    ):
        with rasterio.open(href) as src:
            if src.crs is None or src.count < 1:
                raise SatelliteError("A scene band has no usable coordinate system or pixels.")
            left, bottom, right, top = transform_bounds(
                "EPSG:4326", src.crs, area.west, area.south, area.east, area.north,
                densify_pts=21,
            )
            floating = from_bounds(left, bottom, right, top, transform=src.transform)
            window = floating.round_offsets().round_lengths()
            if (window.width < 1 or window.height < 1 or window.width > 1024 or window.height > 1024):
                raise SatelliteError("The selected area's image window is outside the supported size.")
            if (window.col_off < 0 or window.row_off < 0 or
                    window.col_off + window.width > src.width or
                    window.row_off + window.height > src.height):
                raise SatelliteError("This scene covers only part of the selected rectangle.")
            pixels = src.read(1, window=window, masked=True)
            if pixels.size == 0 or np.ma.count(pixels) < pixels.size * 0.95:
                raise SatelliteError("This scene has incomplete band coverage over the rectangle.")
            return BandWindow(pixels, src.window_transform(window), src.crs)


def _read_aligned_band(href: str, reference: BandWindow) -> np.ma.MaskedArray:
    """Resample only the selected window onto the 10 m red grid."""
    height, width = reference.pixels.shape
    with rasterio.Env(
        GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", GDAL_HTTP_TIMEOUT="15",
        GDAL_HTTP_MAX_RETRY="1", AWS_NO_SIGN_REQUEST="YES",
    ):
        with rasterio.open(href) as src:
            if src.crs is None or src.count < 1:
                raise SatelliteError("A scene layer has no usable coordinate system or pixels.")
            with WarpedVRT(
                src, crs=reference.crs, transform=reference.transform,
                width=width, height=height, resampling=Resampling.nearest,
            ) as aligned:
                return aligned.read(1, masked=True)


def _ndvi(red: np.ma.MaskedArray, nir: np.ma.MaskedArray,
          scl: np.ma.MaskedArray, red_scale: tuple[float, float],
          nir_scale: tuple[float, float]) -> np.ma.MaskedArray:
    """Calculate NDVI from reflectance where both bands and SCL are valid."""
    if red.shape != nir.shape or red.shape != scl.shape:
        raise SatelliteError("The scene layers could not be aligned for NDVI.")
    red_values = red.astype(np.float32).filled(np.nan) * red_scale[0] + red_scale[1]
    nir_values = nir.astype(np.float32).filled(np.nan) * nir_scale[0] + nir_scale[1]
    scl_values = scl.filled(0)
    denominator = nir_values + red_values
    valid = (
        ~np.ma.getmaskarray(red) & ~np.ma.getmaskarray(nir) &
        ~np.ma.getmaskarray(scl) & np.isin(scl_values, CLEAR_SCL_CLASSES) &
        np.isfinite(red_values) & np.isfinite(nir_values) &
        (red_values >= 0) & (nir_values >= 0) & (denominator > 0)
    )
    values = np.zeros(red.shape, dtype=np.float32)
    np.divide(nir_values - red_values, denominator, out=values, where=valid)
    valid &= np.isfinite(values) & (values >= -1) & (values <= 1)
    return np.ma.array(values, mask=~valid)


def _ndvi_png(ndvi: np.ma.MaskedArray) -> bytes:
    """RGBA map: brown below zero, pale near zero, greener as NDVI rises."""
    stops = np.array([-1.0, 0.0, 0.3, 0.6, 1.0])
    colors = np.array([[117, 72, 43], [221, 209, 164], [187, 215, 126],
                       [64, 148, 78], [15, 78, 44]], dtype=np.float32)
    values = np.clip(ndvi.filled(0), -1, 1)
    rgb = np.stack([np.interp(values, stops, colors[:, channel]) for channel in range(3)], axis=-1).astype(np.uint8)
    alpha = (~np.ma.getmaskarray(ndvi)).astype(np.uint8) * 255
    output = io.BytesIO()
    Image.fromarray(np.dstack((rgb, alpha)), mode="RGBA").save(output, format="PNG")
    return output.getvalue()


def _preview_png(pixels: np.ma.MaskedArray) -> bytes:
    """Make a visual grayscale preview; the stretch is not a measurement."""
    valid = pixels.compressed().astype(np.float32)
    if valid.size == 0:
        raise SatelliteError("The scene contains no readable band pixels here.")
    low, high = np.percentile(valid, (2, 98))
    if high <= low:
        high = low + 1
    image = np.clip((pixels.filled(low).astype(np.float32) - low) / (high - low) * 255, 0, 255).astype(np.uint8)
    alpha = (~np.ma.getmaskarray(pixels)).astype(np.uint8) * 255
    output = io.BytesIO()
    Image.fromarray(np.dstack((image, alpha)), mode="LA").save(output, format="PNG")
    return output.getvalue()


def fetch_satellite(area: AnalysisArea, *, now: datetime | None = None) -> SatelliteResult:
    """Try a bounded set of scenes; never substitute another area's image."""
    deadline = time.monotonic() + SATELLITE_BUDGET_SECONDS
    if area.south < -56 or area.north > 84:
        raise NoSceneError("This area is outside Sentinel-2's systematic land coverage (about 56°S to 84°N).")
    candidates = search_scenes(area, now=now)
    if not candidates:
        raise NoSceneError("No recent Sentinel-2 scene with suitable scene-wide cloud metadata was found for this rectangle.")

    best_low_quality = None
    for item in candidates:
        if time.monotonic() >= deadline:
            break
        try:
            red = _read_band(item["assets"]["red"]["href"], area)
            nir = _read_aligned_band(item["assets"]["nir"]["href"], red)
            scl = _read_aligned_band(item["assets"]["scl"]["href"], red)
            if np.ma.count(nir) < nir.size * 0.95:
                raise SatelliteError("This scene has incomplete NIR coverage over the rectangle.")
            ndvi = _ndvi(
                red.pixels, nir, scl,
                _reflectance_scale_offset(item["assets"]["red"]),
                _reflectance_scale_offset(item["assets"]["nir"]),
            )
            valid_count = np.ma.count(ndvi)
            valid_percent = valid_count / ndvi.size * 100
            good_quality = valid_percent >= MIN_VALID_PIXEL_PERCENT
            acquired = datetime.fromisoformat(item["properties"]["datetime"].replace("Z", "+00:00"))
            result = SatelliteResult(
                area=area,
                scene_id=item["id"],
                acquired_at_utc=acquired,
                scene_cloud_percent=float(item["properties"]["eo:cloud_cover"]),
                catalog_url=f"https://earth-search.aws.element84.com/v1/collections/{COLLECTION}/items/{item['id']}",
                fetched_at_utc=datetime.now(timezone.utc),
                red_preview_png=_preview_png(red.pixels),
                nir_preview_png=_preview_png(nir),
                ndvi_png=_ndvi_png(ndvi) if good_quality else None,
                mean_ndvi=float(np.ma.mean(ndvi)) if good_quality else None,
                median_ndvi=float(np.ma.median(ndvi)) if good_quality else None,
                valid_pixel_percent=valid_percent,
                quality_message=None if good_quality else
                    "Too few clear, valid pixels in this rectangle for a reliable NDVI summary.",
                width=red.pixels.shape[1],
                height=red.pixels.shape[0],
            )
            if good_quality:
                return result
            if best_low_quality is None or result.valid_pixel_percent > best_low_quality.valid_pixel_percent:
                best_low_quality = result
        except (SatelliteError, RasterioError, OSError, ValueError):
            continue
    if best_low_quality is not None:
        return best_low_quality
    raise NoSceneError("Recent scenes were found, but none fully covered this rectangle with readable red, NIR, and classification pixels. Try again later or select another area.")
