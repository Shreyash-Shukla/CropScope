# CropScope

CropScope is a small precision-farming decision-support prototype. Its first working slice lets a user select a **rectangular analysis area anywhere on the map** and fetch a live seven-day weather forecast for that area's centre. Satellite imagery, NDVI, and AI-assisted recommendations are planned for later phases.

## Run locally

Requires Python 3.13 and an internet connection. In PowerShell:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Open the local URL printed by Streamlit. No API key is required for Phase 1.

## Select an area and analyze

1. Choose **Draw on map**. Zoom to the field, select the rectangle tool at the top left of the map, and drag across the land. Use the trash tool to remove an old drawing before drawing another. The map shows the outline, and CropScope shows its approximate area and edge coordinates.
2. Alternatively, choose **Enter coordinates** and supply north, south, east, and west in decimal degrees. A preview map shows the outline. **Use Karnal example** provides a quick sample only; it is not required for other locations.
3. Enter the crop and growth stage, then click **Analyze**. The weather request uses the rectangle's centre. Crop and stage are recorded for later recommendation features; they do not affect the weather data.

The supported rectangle size is 0.01–9 km², with each side at most 5 km. A rectangle must have south below north and west left of east. Rectangles crossing the 180° meridian need to be drawn on one side at a time. These limits keep later 10 m satellite reads practical. The selected rectangle is an **analysis area**, not a surveyed field boundary; it may include non-crop land.

## Current result

The app shows seven local dates, daily precipitation sum (mm), maximum 2 m air temperature (°C), and FAO reference evapotranspiration ET₀ (mm). The table and charts identify the source, forecast time zone, and UTC fetch time. The forecast comes from the [Open-Meteo Forecast API](https://open-meteo.com/en/docs), which returns a gridded reading for the selected centre. It is predicted weather, not a field measurement. ET₀ describes a reference grass surface and is **not** an irrigation prescription. If the weather service fails, the app shows an error and allows a retry for the same area.

The saved Karnal example is **29.748–29.752° N, 77.048–77.052° E**. On 25 October 2026, the public [Element 84 Earth Search STAC API](https://github.com/Element84/earth-search) returned Sentinel-2 Level-2A item `S2B_T43RFN_20261025T053358_L2A` intersecting it. This confirms scene availability only; field content and pixel quality need checking in Phase 2.

## Scope and secrets

The [build plan](BUILD_PLAN.md) sets out foundation, selected-area weather, satellite scene selection, cloud-masked NDVI, AI-assisted recommendations, and demo hardening. Phase 1 ends with a fresh, dated forecast for a user-selected area. No IoT hardware or model training is in scope.

Future API keys belong in local environment variables or `.streamlit/secrets.toml`, both excluded from Git. Never commit a key.
