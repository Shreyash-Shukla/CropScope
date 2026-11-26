# CropScope: two-minute demo

Prepare with `streamlit run app.py`. Keep the Karnal example available as a backup. The saved example was fetched on 30 October 2026 and must be described as dated historical data if used later.

**0:00–0:25 — Select an area.** Show the world map under **Draw on map** (labelled satellite hybrid view with village/road overlays) and draw one tight rectangle over agricultural land. Point out the outlined analysis area in hectares and acres. If map interaction is slow, use **Search location**, **Use my location**, **Enter coordinates**, or **Use sample preset** (Karnal backup shortcut).

**0:25–0:55 — Weather & Crop Water Plan.** Enter the crop and growth stage and press **ANALYZE SATELLITE PASSES →**. Show the seven dated daily rows for rain, rain probability, max/min temperature, wind speed, humidity, GDD, and reference ET₀, along with the **Crop-Specific Water Planner (FAO-56 ETc)** and **Field Operations Planner**. Explain that Open-Meteo estimates weather for the rectangle's centre and that ET₀ / ETc are atmospheric estimates, not measured soil water readings.

**0:55–1:25 — Satellite & Spatial Scouting.** Show the Sentinel-2 scene ID, acquisition date, True Color (TCI) photo alongside cloud-masked NDVI (plus the colorblind-safe Viridis toggle), canopy uniformity, the **4-Quadrant Scouting Compass (NW/NE/SW/SE)**, and the **Georeferenced NDVI Field Overlay** map. Explain that the rectangle can include non-crop land and NDVI indicates greenness rather than disease or yield.

**1:25–1:50 — Checks, Exports & Kisan Mitra.** Show the evidence under each suggestion (**Gemini-ranked** or **Rule-based fallback**), the **WhatsApp / SMS Field Brief**, **Printable HTML Report**, and the **Kisan Mitra** multilingual advisor.

**1:50–2:00 — Reliability.** Explain that weather and satellite can fail independently. **USE SAVED ARCHIVE SCENE** shows original dates and a saved label. It never uses Karnal data for another rectangle.

For a network outage, choose **Use sample preset**, enter a crop and stage, then press **USE SAVED ARCHIVE SCENE**. Say the forecast dates and scene acquisition date aloud. Retry live later when the services return.
