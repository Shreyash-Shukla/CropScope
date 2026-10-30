# CropScope

CropScope is a small precision-farming decision-support prototype. A user can select a **rectangular analysis area anywhere on the map**, fetch a live seven-day weather forecast for its centre, retrieve a recent Sentinel-2 Level-2A scene with cloud-masked NDVI, and see up to three evidence-backed field checks. Gemini can rank the checks when a local key is configured; a labeled rule-based fallback works without one.

## Run locally

Requires Python 3.13 and an internet connection. In PowerShell:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Open the local URL printed by Streamlit. Weather, satellite results, and rule-based checks need no key. To enable Gemini ranking, copy `.env.example` to `.env` and set `GEMINI_API_KEY` in that ignored local file, or set the variable in the shell that starts Streamlit. Do not put the key in a tracked file or chat message. A live Gemini ranking was verified on 31 October 2026.

## Select an area and analyze

1. Choose **Draw on map**. Zoom to the field, select the rectangle tool at the top left of the map, and drag across the land. Use the trash tool to remove an old drawing before drawing another. The map shows the outline, and CropScope shows its approximate area and edge coordinates.
2. Alternatively, choose **Enter coordinates** and supply north, south, east, and west in decimal degrees. A preview map shows the outline. **Use Karnal example** provides a quick sample only; it is not required for other locations.
3. Enter the crop and growth stage, then click **Analyze / retry live**. The weather request uses the rectangle's centre. The satellite catalog search uses all four rectangle edges, and image reads are limited to the selected area. Crop and stage inform action wording, but do not change or verify the source observations.

The supported rectangle size is 0.01–9 km², with each side at most 5 km. A rectangle must have south below north and west left of east. Rectangles crossing the 180° meridian need to be drawn on one side at a time. These limits keep later 10 m satellite reads practical. The selected rectangle is an **analysis area**, not a surveyed field boundary; it may include non-crop land.

## Current results

The app shows seven local dates, daily forecast rain (mm), maximum 2 m air temperature (°C), and FAO reference evapotranspiration ET₀ (mm). The table and charts identify the source, forecast time zone, and UTC fetch time. The forecast comes from the [Open-Meteo Forecast API](https://open-meteo.com/en/docs), which returns a gridded reading for the selected centre. It is predicted weather, not a field measurement. ET₀ describes a reference grass surface and is **not** an irrigation prescription. If the weather service fails, the app shows an error and allows a retry for the same area.

The satellite section searches the previous 35 days in the [Element 84 Earth Search STAC catalog](https://github.com/Element84/earth-search), considers scenes with at most 60% **scene-wide** cloud metadata, and attempts up to four promising scenes. It shows the chosen scene ID, acquisition and fetch times, cloud metadata, and cropped 10 m red (B04) and near-infrared (B08) previews. Each preview is contrast-enhanced for viewing. NDVI uses each asset's STAC scale and offset to convert band values to reflectance, aligns the 20 m scene-classification layer to the 10 m red grid by nearest-neighbor resampling, and excludes no-data, cloud, shadow, snow, uncertain, and invalid-reflectance pixels. Clear vegetation, bare soil, and water pixels are eligible. The app shows the usable-pixel percentage within the rectangle, mean and median NDVI, and a transparent-masked NDVI image. If fewer than 10% of pixels are usable, it tries another candidate scene and otherwise shows a quality message without a vegetation summary. Scene-wide cloud metadata alone does not measure quality in the selected rectangle. NDVI describes greenness; one image cannot identify a disease, prove crop type, or measure yield.

Weather and satellite requests have separate loading and failure states: a failure in one still allows the other result to appear. Open-Meteo and catalog requests have 20-second network timeouts; image reads have 15-second network timeouts and a four-scene, 90-second candidate budget. If no recent suitable scene fully covers the rectangle, the app explains that and leaves the weather result available. Sentinel-2 systematic land coverage is approximately 56°S–84°N. The public catalog and image assets are best-effort services, so retrying may help after an outage.

Code proposes a finite set of checks based on available forecast or usable NDVI evidence. Gemini 3.1 Flash-Lite, when configured, can only rank those checks and select their evidence IDs. Its request has a 30-second timeout. The app validates every ID and displays code-controlled wording, so a malformed response falls back to the labeled rule order. If both sources fail and no same-area cache exists, it shows no recommendation. Suggestions do not assert soil moisture, diagnose disease, or prescribe irrigation or fertilizer amounts.

Each successful live source is saved locally under `cache/`. A failed live request may display a saved result **only for the exact same rectangle**; **Use saved result for this rectangle** loads it without a network request. Saved results are explicitly labeled and retain the original forecast, acquisition, and fetch dates. A dated Karnal example is bundled in `sample_data/` for an offline demo. It is never substituted for a different rectangle. An old saved forecast is historical, not a current prediction.

The saved Karnal example is **29.748–29.752° N, 77.048–77.052° E**. `sample_data/karnal_scene.json` retains the Phase 2 reference metadata; the keyed JSON files contain the dated Phase 5 weather and NDVI demo cache. [Karnal NDVI](screenshots/karnal_ndvi.png) and [rule-based suggestions](screenshots/karnal_suggestions.png) are screenshots from a live app run on 30 October 2026, before the key was configured. A separate [Gemini-ranked result](screenshots/karnal_gemini.png) was captured on 31 October from the explicitly labeled saved same-area data. The [two-minute demo script](DEMO.md) identifies what to show and how to use the backup cache. The [updated presentation](presentation/CropScope_Demo_2026-10-31.pptx) uses the observed results and records the later live Gemini validation.

To run focused checks:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe scripts\live_check.py
.\.venv\Scripts\python.exe scripts\check_gemini.py
```

The live check writes only to ignored `cache/`. Add `--refresh-demo-cache` to intentionally replace the dated Karnal sample in `sample_data/` after checking its provenance.

## Scope and secrets

The [build plan](BUILD_PLAN.md) records the implementation and acceptance gates. Live weather and satellite checks completed for distinct rectangles in India, France, and Australia on 30 October 2026. A live Gemini 3.1 Flash-Lite call completed on 31 October 2026 and returned verified action and evidence IDs. No IoT hardware or model training is in scope.

API keys belong in local environment variables or the ignored `.env` file. Never commit a key.
