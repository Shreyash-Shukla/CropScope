# CropScope — build plan

**Scope agreed on 25 October 2026; status updated 31 October 2026.** Build a small, separate Python application called **CropScope**. Phases 0–5 are complete. Three map-drawn areas in India, France, and Australia returned live weather and satellite results. A live Gemini 3.1 Flash-Lite call ranked three code-defined checks using only their required evidence IDs. The app retains a labeled rule-based fallback when Gemini is unavailable.

## 1. What the finished prototype will do

For a user-selected agricultural analysis area, CropScope will combine:

1. A dated seven-day weather forecast: daily rain, maximum temperature, and reference evapotranspiration (ET₀).
2. A dated Sentinel-2 Level-2A observation: red and near-infrared imagery, a cloud-masked NDVI image, a vegetation summary, and the percentage of usable pixels.
3. The user's crop and growth stage, entered manually.
4. AI-ranked, plain-language management suggestions tied to the observations shown on screen.

The demo should answer: **“What is happening in this area, what weather is coming, and what should the farmer check or consider next?”** It is a decision-support prototype, not an automated agronomy or irrigation system.

### Main demo path

Zoom to any supported agricultural location on an interactive world map → choose **Draw rectangle** → click and drag across the land to be analyzed, like a desktop selection box → see the outlined area and its approximate size → select crop and growth stage → click **Analyze**. As an accessibility/precision alternative, enter the rectangle's north, south, east, and west coordinates. A single point is not enough to define the satellite analysis area. A saved example is only a one-click demo shortcut, never a replacement for a user's selection.

### Honest boundaries

- The selected rectangle is an **analysis area**, not a surveyed field boundary. It can contain non-crop pixels and should be drawn tightly around one field. Show the rectangle on the map and let the user redraw it. Very large or tiny rectangles will receive a size warning or require resizing before analysis.
- Sentinel-2 does not systematically image every latitude: the initial satellite feature supports its land-coverage zone (roughly 56°S to 83–84°N, depending on the mission document). Outside coverage, or where no sufficiently clear recent scene exists, explain that satellite analysis is unavailable rather than inventing a result. Weather can still be shown if available.
- NDVI indicates vegetation greenness; one image cannot identify a disease, prove a crop type, or measure yield.
- Without soil measurements, suggestions may say “check soil moisture” but cannot assert soil moisture or prescribe exact irrigation volume or fertilizer dose.
- No IoT, blockchain, accounts, database, model training, disease classifier, yield prediction, automated actuation, or mobile app in this build.
- The demo will distinguish live results from a dated cached result. It will never present cached observations as current.

## 2. Technical design

| Component | Choice | Reason |
| --- | --- | --- |
| User interface | Streamlit | A single Python application is fast to build and easy to demonstrate locally. |
| Weather | Open-Meteo Forecast API | A seven-day JSON forecast with the required daily variables. |
| Satellite search | Element 84 Earth Search STAC, Sentinel-2 Level-2A | Public searchable scene metadata and cloud-optimized band assets. |
| Location selection | Folium Draw rectangle in Streamlit, plus four-corner coordinate entry | The user can visibly select the whole area at any supported location. |
| Image processing | Rasterio + NumPy | Read only the area of interest, align/mask pixels, and calculate NDVI. |
| AI | Gemini API via `google-genai` | One API call ranks and explains safe candidate actions; no training. |
| Reproducibility | Small dated local demo cache | Keeps the presentation usable during a network or public-API outage. |

**Data flow:** drawn/entered rectangle → validate its geographic extent and size → use its centre for the area-representative weather forecast while searching STAC with the whole rectangle → crop/mask satellite pixels inside the rectangle → small rule set proposes candidate actions → AI ranks/explains those actions from structured evidence → validation → results page. The weather source is a gridded forecast, so its centre-point reading is not a separate measurement at every pixel.

### Availability, latency, and failure behaviour

Both services can be queried for a newly drawn area. Open-Meteo's default forecast provides global coordinate coverage. Its free API allows non-commercial educational use without a key or sign-up, requires attribution, and currently limits free use to fewer than 10,000 calls per day. Sentinel data are free and open; Earth Search exposes a free public STAC catalog and public imagery assets, but operates on a best-effort basis. Neither source guarantees uninterrupted service. Sentinel-2's systematic land coverage does not include every latitude and cloud-free pixels are not guaranteed on a particular date.

**Measurements on 25 October 2026 from this computer (three arbitrary regions; small requests; not a service guarantee):**

| Region | Seven-day weather JSON | Sentinel catalog search | Red + NIR + classification image-window reads |
| --- | ---: | ---: | ---: |
| Near Karnal, India | 1.40 s | 0.92 s | 7.93 s |
| Farmland in France | 0.24 s | 0.49 s | 8.71 s |
| Farmland in Australia | 0.20 s | 1.11 s | 8.42 s |

The last column reads only a roughly 400 m-wide image window. It does not include searching several cloudy candidates, NDVI processing, AI latency, or page rendering. **Planning expectation:** weather often appears in a few seconds, while a first uncached satellite analysis may take tens of seconds. We will measure full end-to-end time after implementation rather than promise a fixed completion time. Repeating an identical request should be quicker through caching.

Fetch weather and satellite data independently, show progress labels (weather → searching scenes → reading bands → processing → AI), and show each section as soon as it is ready. Set finite request/time budgets and offer **Retry**. If weather fails, show satellite results and only satellite-supported suggestions. If imagery is unavailable, show weather and only weather-supported suggestions. If both fail, show a clear unavailable state and no generated recommendation. A cached result can be shown only for the **same selected rectangle**, with its original observation/fetch date and an explicit cached label; never substitute the demo area's data for another area. Search a wider recent date window and a few candidate scenes when clouds obstruct the first scene, but show the image date and stop after a bounded effort.

**Satellite correctness requirements:** use the red and near-infrared asset scale *and offset* supplied in STAC metadata before calculating `(NIR − Red) / (NIR + Red)`; align the scene-classification raster to the 10 m bands with nearest-neighbor resampling; mask no-data, clouds, shadows, and other invalid pixels. Display the selected scene ID, acquisition date, scene cloud metadata, and valid-pixel percentage. Scene-wide cloud percentage alone is insufficient to judge the selected area.

**AI guardrails:** code generates a finite list of action IDs from the weather, crop/stage, and vegetation observations. AI returns a structured ranking and supporting evidence IDs. Code supplies the displayed action wording and evidence explanation, preventing generated measurements or input prescriptions from reaching the page. Code rejects unknown action IDs, missing evidence, and malformed output. If the AI service fails, show a clearly marked rule-based fallback; the final project must also demonstrate at least one successful live AI call.

## 3. Phases and acceptance gates

| Phase | Work | Done when |
| --- | --- | --- |
| **0 — Foundation** (about 1–2 hours) | Create a clean `CropScope` project and virtual environment; pin a small dependency set; define rectangle/coordinate validation, data structures, and secret handling; confirm one example scene. | The app starts locally; analysis geometry is represented independently of any example; no secret appears in the repository. |
| **1 — Draw area + weather vertical slice** (about 5–7 hours) | Build the draggable map rectangle, north/south/east/west entry, redraw/size validation, crop/stage form, and results layout; fetch seven daily rows of rain, maximum temperature, and ET₀; show dates, units, source, and errors. | A user draws a new area, sees its outline, and receives its own real, dated forecast. This is the earliest honest progress demo. |
| **2 — Satellite acquisition** (about 1 day) | Search scenes from the submitted area's geometry in a recent date window, choose a suitable intersecting scene, record provenance, read only small cloud-optimized GeoTIFF windows, and save one dated example. | Two user-selected locations in different regions return their own scene metadata and cropped visuals, or a clear no-scene message. |
| **3 — Vegetation processing** (about 1 day) | Apply band scale/offset, align the scene-classification layer, mask unusable pixels, calculate NDVI and mean/median/valid fraction, render the image, handle no-data scenes. | A known-value pixel check matches the expected NDVI; two geographically distinct user-selected areas produce their own image/summary or an honest quality message. |
| **4 — Recommendations and AI** (about 1 day) | Generate safe candidate actions with transparent rules; send structured observations to Gemini; validate the structured reply; display up to three ranked suggestions and their evidence. | One live AI call completes; suggestions use only supplied facts and survive a malformed or unavailable AI response. |
| **5 — Finish and present** (about 1 day) | Add independent loading/failure states, finite timeouts, same-area cache labels, credits, run instructions, focused tests, screenshots, and a two-minute demo script. Update the presentation only with results actually obtained. | At least three drawn agricultural areas in different parts of the world are exercised; weather-only, satellite-only, neither-source, fresh, and same-area cached cases behave correctly; another student can run the project from the README. |

The phases are sequential. Arbitrary location selection is **core scope**, not a stretch feature. If time becomes tight, simplify crop-specific wording or visual polish, but keep the ability to submit any valid location. The saved example only protects the live presentation from an external-service outage.

## 4. Proposed project layout

```text
CropScope/
  app.py                 # Streamlit inputs, charts/images, result states
  location.py            # drawn rectangle GeoJSON, coordinate entry, validation
  weather.py             # Open-Meteo fetch and validation
  satellite.py           # STAC search, band windows, masks, NDVI
  recommendations.py     # finite, inspectable candidate-action rules
  ai.py                  # Gemini request, structured output, validation
  models.py              # small typed input/result structures
  sample_data/           # dated, attributed demo cache
  tests/                 # focused math and failure-path checks
  requirements.txt
  .env.example           # variable names only
  README.md              # setup, data sources, demo, limitations
```

This repository is the farming implementation, separate from the presentation workspace and the previous carbon-credit project. The app runs on Python 3.13 with Rasterio 1.4.4.

## 5. What each teammate can own

| Shreyash | Parth | Shared review |
| --- | --- | --- |
| Streamlit page, weather request, final integration and live demo | Satellite search, NDVI pipeline, sample scene metadata | AI action wording, screenshots, README, and checking that presentation claims match the code |

This is a suggested split, not a dependency: either person can take either module. Agree on the `WeatherResult` and `SatelliteResult` fields before working separately so integration is a simple function call.

## 6. Checks worth doing

- NDVI: test known red/NIR values **after scale and offset**, division by zero, and the cloud/invalid-pixel mask.
- External data: test invalid/inverted rectangle coordinates, a changed drawing, oversize/tiny rectangle, an area crossing a map boundary, incomplete forecast response, no STAC scene, and a scene with too few usable pixels.
- Global path: draw farmland rectangles in India, Europe, and a Southern Hemisphere region. Verify that each request uses its own geometry and never silently substitutes the saved example.
- Failure path: simulate weather-only, satellite-only, neither-source, timeout, and same-area cached results; ensure the AI cannot cite missing observations.
- AI: test unknown action/evidence IDs, invalid JSON or schema, and service failure.
- Demo: run once with live services and once with the clearly dated local cache; verify all visible dates and source labels.

## 7. Decisions needed before or during the build

1. **Name:** CropScope — selected.
2. **Location:** user-drawn rectangles are required. A checked area near Karnal, Haryana, will be included only as a convenient demo example. If you have a real plot you can identify, we can use it for the scripted demo.
3. **Crop/stage:** manual user input in the app. For the scripted demo, choose a crop and stage that match the selected area's season; do not infer crop type from the satellite scene.
4. **AI key:** a Gemini API key will be needed by Phase 4, stored in a local environment variable. It must not be sent to me or committed.
5. **Presentation:** keep the current proposal deck's Results/Demo slide as “features in progress” until the corresponding phase works. Then replace it with screenshots and observed results.

## 8. Source documentation

- Open-Meteo forecast variables and API: https://open-meteo.com/en/docs
- Element 84 Earth Search STAC API: https://github.com/Element84/earth-search/blob/main/README.md
- Sentinel-2 NDVI formula background: https://www.usgs.gov/landsat-missions/landsat-normalized-difference-vegetation-index
- Gemini API setup: https://ai.google.dev/gemini-api/docs/get-started
- Gemini structured output: https://ai.google.dev/gemini-api/docs/structured-output
- Streamlit installation and execution: https://docs.streamlit.io/get-started/installation
- Streamlit-Folium map interaction: https://github.com/randyzwitch/streamlit-folium
- Folium's rectangle drawing tool: https://python-visualization.github.io/folium/v0.19.5/user_guide/plugins/draw.html
- Sentinel-2 geographic coverage: https://sentinels.copernicus.eu/documents/247904/685211/Sentinel-2_User_Handbook
- Open-Meteo free API terms: https://open-meteo.com/en/terms
- Copernicus free and open Sentinel data: https://sentinels.copernicus.eu/sentinel-data-access-description
