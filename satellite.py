"""Find a recent Sentinel-2 scene and read only the selected area's band windows.

Phase 2 previews are contrast-enhanced raw band values. Reflectance scaling,
cloud masking, and NDVI belong to Phase 3.
"""

import io
import json
import math
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import numpy as np
import rasterio
from PIL import Image
from rasterio.errors import RasterioError
from rasterio.warp import transform_bounds
from rasterio.windows import from_bounds

from models import AnalysisArea, SatelliteResult


SEARCH_URL = "https://earth-search.aws.element84.com/v1/search"
COLLECTION = "sentinel-2-c1-l2a"
LOOKBACK_DAYS = 35
MAX_SCENE_CLOUD_PERCENT = 60.0
MAX_CANDIDATES = 4


class SatelliteError(Exception):
    """Satellite metadata or pixels could not be retrieved safely."""


class NoSceneError(SatelliteError):
    """No usable recent scene was found for this rectangle."""


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
            if not all(isinstance(assets[band]["href"], str) and assets[band]["href"].startswith("https://") for band in ("red", "nir")):
                continue
            if not (acquired.tzinfo and start <= acquired <= now and math.isfinite(cloud) and 0 <= cloud <= MAX_SCENE_CLOUD_PERCENT):
                continue
            candidates.append(item)
        except (KeyError, TypeError, ValueError, OverflowError):
            continue

    candidates.sort(key=lambda item: (
        float(item["properties"]["eo:cloud_cover"]) +
        (now - datetime.fromisoformat(item["properties"]["datetime"].replace("Z", "+00:00"))).total_seconds() / 86400 * 0.4,
        item["id"],
    ))
    return candidates[:MAX_CANDIDATES]


def _read_band(href: str, area: AnalysisArea) -> np.ma.MaskedArray:
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
            return pixels


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
    if area.south < -56 or area.north > 84:
        raise NoSceneError("This area is outside Sentinel-2's systematic land coverage (about 56°S to 84°N).")
    candidates = search_scenes(area, now=now)
    if not candidates:
        raise NoSceneError("No recent Sentinel-2 scene with suitable scene-wide cloud metadata was found for this rectangle.")

    for item in candidates:
        try:
            red = _read_band(item["assets"]["red"]["href"], area)
            nir = _read_band(item["assets"]["nir"]["href"], area)
            acquired = datetime.fromisoformat(item["properties"]["datetime"].replace("Z", "+00:00"))
            return SatelliteResult(
                area=area,
                scene_id=item["id"],
                acquired_at_utc=acquired,
                scene_cloud_percent=float(item["properties"]["eo:cloud_cover"]),
                catalog_url=f"https://earth-search.aws.element84.com/v1/collections/{COLLECTION}/items/{item['id']}",
                fetched_at_utc=datetime.now(timezone.utc),
                red_preview_png=_preview_png(red),
                nir_preview_png=_preview_png(nir),
                width=red.shape[1],
                height=red.shape[0],
            )
        except (SatelliteError, RasterioError, OSError, ValueError):
            continue
    raise NoSceneError("Recent scenes were found, but none fully covered this rectangle with readable red and NIR pixels. Try again later or select another area.")
