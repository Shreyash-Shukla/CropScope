"""Exercise three distinct selected rectangles against live public sources."""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analysis import analyze
from cache import CacheStore
from location import SAMPLE_AREA, validate_rectangle
from models import AnalysisRequest


ROOT = Path(__file__).resolve().parents[1]
AREAS = (
    ("Karnal, India", SAMPLE_AREA),
    ("Central France", validate_rectangle(47.000, 2.000, 47.004, 2.004)),
    ("New South Wales, Australia", validate_rectangle(-34.280, 146.050, -34.276, 146.054)),
)


def main() -> None:
    for index, (label, area) in enumerate(AREAS):
        store = CacheStore(ROOT / "cache")
        started = time.monotonic()
        outcome = analyze(AnalysisRequest(area, "crop to verify", "Vegetative"), store)
        weather, satellite = outcome.weather.result, outcome.satellite.result
        print(f"{label}: {time.monotonic() - started:.1f}s", flush=True)
        print(f"  Weather: {weather.days[0].day} to {weather.days[-1].day}" if weather else
              f"  Weather unavailable: {outcome.weather.error}", flush=True)
        print(f"  Satellite: {satellite.scene_id}, NDVI {satellite.mean_ndvi}, "
              f"usable {satellite.valid_pixel_percent:.1f}%" if satellite else
              f"  Satellite unavailable: {outcome.satellite.error}", flush=True)
        print(f"  Suggestions: {outcome.suggestion_source} ({len(outcome.suggestions)})", flush=True)
        assert weather is not None and weather.area == area and not outcome.weather.cached
        assert satellite is not None and satellite.area == area and not outcome.satellite.cached
        if index == 0 and "--refresh-demo-cache" in sys.argv:
            demo_store = CacheStore(ROOT / "sample_data")
            demo_store.save_weather(weather)
            demo_store.save_satellite(satellite)


if __name__ == "__main__":
    main()
