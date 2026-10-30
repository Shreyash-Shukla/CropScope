# CropScope

CropScope is a small precision-farming decision-support prototype. A user can select a **rectangular analysis area anywhere on the map**, fetch a live seven-day weather forecast for its centre, and retrieve a recent Sentinel-2 Level-2A scene with cloud-masked NDVI and cropped red and near-infrared previews. AI-assisted recommendations are planned for a later phase.

## Run locally

Requires Python 3.13 and an internet connection. In PowerShell:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Open the local URL printed by Streamlit. No API key is required for Phases 1–3.

## Select an area and analyze

1. Choose **Draw on map**. Zoom to the field, select the rectangle tool at the top left of the map, and drag across the land. Use the trash tool to remove an old drawing before drawing another. The map shows the outline, and CropScope shows its approximate area and edge coordinates.
2. Alternatively, choose **Enter coordinates** and supply north, south, east, and west in decimal degrees. A preview map shows the outline. **Use Karnal example** provides a quick sample only; it is not required for other locations.
3. Enter the crop and growth stage, then click **Analyze**. The weather request uses the rectangle's centre. The satellite catalog search uses all four rectangle edges, and image reads are limited to the selected area. Crop and stage are recorded for later recommendation features; they do not affect these data sources.

The supported rectangle size is 0.01–9 km², with each side at most 5 km. A rectangle must have south below north and west left of east. Rectangles crossing the 180° meridian need to be drawn on one side at a time. These limits keep later 10 m satellite reads practical. The selected rectangle is an **analysis area**, not a surveyed field boundary; it may include non-crop land.

## Current results

The app shows seven local dates, daily forecast rain (mm), maximum 2 m air temperature (°C), and FAO reference evapotranspiration ET₀ (mm). The table and charts identify the source, forecast time zone, and UTC fetch time. The forecast comes from the [Open-Meteo Forecast API](https://open-meteo.com/en/docs), which returns a gridded reading for the selected centre. It is predicted weather, not a field measurement. ET₀ describes a reference grass surface and is **not** an irrigation prescription. If the weather service fails, the app shows an error and allows a retry for the same area.

The satellite section searches the previous 35 days in the [Element 84 Earth Search STAC catalog](https://github.com/Element84/earth-search), considers scenes with at most 60% **scene-wide** cloud metadata, and attempts up to four promising scenes. It shows the chosen scene ID, acquisition and fetch times, cloud metadata, and cropped 10 m red (B04) and near-infrared (B08) previews. Each preview is contrast-enhanced for viewing. NDVI uses each asset's STAC scale and offset to convert band values to reflectance, aligns the 20 m scene-classification layer to the 10 m red grid by nearest-neighbor resampling, and excludes no-data, cloud, shadow, snow, uncertain, and invalid-reflectance pixels. Clear vegetation, bare soil, and water pixels are eligible. The app shows the usable-pixel percentage within the rectangle, mean and median NDVI, and a transparent-masked NDVI image. If fewer than 10% of pixels are usable, it tries another candidate scene and otherwise shows a quality message without a vegetation summary. Scene-wide cloud metadata alone does not measure quality in the selected rectangle. NDVI describes greenness; one image cannot identify a disease, prove crop type, or measure yield.

Weather and satellite requests are independent: a failure in one still allows the other result to appear. If no recent suitable scene fully covers the rectangle, the app explains that and leaves the weather result available. Sentinel-2 systematic land coverage is approximately 56°S–84°N. The public catalog and image assets are best-effort services, so retrying may help after an outage.

The saved Karnal example is **29.748–29.752° N, 77.048–77.052° E**. `sample_data/karnal_scene.json` records a dated Phase 2 acquisition, source, and exact rectangle, with two captured PNG previews. These are reference artifacts only; the app never substitutes them for an arbitrary user-selected area.

To run focused checks:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

## Scope and secrets

The [build plan](BUILD_PLAN.md) sets out foundation, selected-area weather, satellite scene selection, cloud-masked NDVI, AI-assisted recommendations, and demo hardening. Phase 3 adds area-specific NDVI and quality reporting; recommendations and demo hardening remain planned. No IoT hardware or model training is in scope.

Future API keys belong in local environment variables or `.streamlit/secrets.toml`, both excluded from Git. Never commit a key.
