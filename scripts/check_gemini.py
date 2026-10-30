"""Run one live Gemini ranking against the dated, exact-area Karnal example."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ai import AIError, rank_with_gemini
from cache import CacheStore
from location import SAMPLE_AREA
from models import AnalysisRequest
from recommendations import build_candidates


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    store = CacheStore(ROOT / "cache", ROOT / "sample_data")
    weather = store.load_weather(SAMPLE_AREA)
    satellite = store.load_satellite(SAMPLE_AREA)
    if weather is None or satellite is None:
        raise SystemExit("The exact-area Karnal sample is missing.")
    request = AnalysisRequest(SAMPLE_AREA, "wheat", "Vegetative")
    evidence, candidates = build_candidates(request, weather, satellite)
    try:
        selected = rank_with_gemini(request, evidence, candidates)
    except AIError as exc:
        cause = exc.__cause__
        print(f"Gemini check failed: {exc} (cause type: {type(cause).__name__}; "
              f"status: {getattr(cause, 'code', 'unknown')})")
        raise SystemExit(1) from None
    print("Live Gemini ranking validated against the dated Karnal evidence:")
    for suggestion in selected:
        print(f"  {suggestion.candidate.id}: {', '.join(item.id for item in suggestion.evidence)}")


if __name__ == "__main__":
    main()
