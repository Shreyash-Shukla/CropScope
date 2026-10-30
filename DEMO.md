# CropScope: two-minute demo

Prepare with `streamlit run app.py`. Keep the Karnal example available as a backup. The saved example was fetched on 30 October 2026 and must be described as dated historical data if used later.

**0:00–0:25 — Select an area.** Show the world map and draw one tight rectangle over agricultural land. Point out the outlined analysis area and its approximate size. If the map interaction is slow, enter the four edge coordinates instead. The Karnal example is the backup shortcut.

**0:25–0:55 — Weather.** Enter the crop and growth stage and press **Analyze / retry live**. Show the seven dated daily rows for rain, maximum temperature, and reference ET₀. Explain that Open-Meteo estimates weather for the rectangle's centre and that ET₀ is not a measured soil water deficit.

**0:55–1:25 — Satellite.** Show the Sentinel-2 scene ID and acquisition date, the usable-pixel percentage, and the cloud-masked NDVI image with mean and median. Explain that the rectangle can include non-crop land and NDVI indicates greenness rather than disease or yield.

**1:25–1:50 — Checks.** Show the evidence under each suggestion. State whether the banner says **Gemini-ranked** or **Rule-based fallback**. A live Gemini ranking completed on 31 October 2026; the dated 30 October screenshot in the presentation shows the fallback before the key was configured.

**1:50–2:00 — Reliability.** Explain that weather and satellite can fail independently. **Use saved result for this rectangle** shows original dates and a saved label. It never uses Karnal data for another rectangle.

For a network outage, choose **Use Karnal example**, enter a crop and stage, then press **Use saved result for this rectangle**. Say the forecast dates and scene acquisition date aloud. Retry live later when the services return.
