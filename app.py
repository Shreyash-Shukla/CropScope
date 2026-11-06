"""CropScope: selected-area weather and Sentinel-2 vegetation processing."""

import folium
import pandas as pd
import streamlit as st
from pathlib import Path
from folium.plugins import Draw, Geocoder
from streamlit_folium import st_folium

from agronomy import compute_agro_climatic_summary, evaluate_operational_windows
from analysis import AnalysisOutcome, SourceState, analyze as run_analysis
from cache import CacheStore
from location import LocationError, SAMPLE_AREA, SAMPLE_PRESETS, rectangle_from_geojson, validate_rectangle
from models import AnalysisArea, AnalysisRequest, SatelliteResult, WeatherResult
from reporting import generate_advisory_json, generate_advisory_markdown


def add_map_layers(map_obj: folium.Map) -> None:
    folium.TileLayer(
        tiles="https://cartodb-basemaps-{s}.global.ssl.fastly.net/light_all/{z}/{x}/{y}.png",
        attr="&copy; OpenStreetMap &copy; CartoDB",
        name="Day / Light Mode",
    ).add_to(map_obj)
    folium.TileLayer(
        tiles="https://cartodb-basemaps-{s}.global.ssl.fastly.net/dark_all/{z}/{x}/{y}.png",
        attr="&copy; OpenStreetMap &copy; CartoDB",
        name="Night / Dark Mode",
    ).add_to(map_obj)
    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="&copy; Esri World Imagery",
        name="Satellite View",
    ).add_to(map_obj)
    folium.LayerControl(position="topright", collapsed=True).add_to(map_obj)


def draw_area() -> tuple[AnalysisArea | None, str | None]:
    st.write("Zoom to your location, choose the rectangle tool at the top left, and drag across one field. Use the layer icon (top right) to switch between Day/Night/Satellite maps. Use the trash tool to clear before drawing another.")
    map_view = folium.Map(location=[18, 0], zoom_start=2, control_scale=True)
    add_map_layers(map_view)
    Geocoder(collapsed=True).add_to(map_view)
    Draw(
        export=False,
        draw_options={"rectangle": True, "polyline": False, "polygon": False, "circle": False, "circlemarker": False, "marker": False},
        edit_options={"edit": True, "remove": True},
    ).add_to(map_view)
    map_state = st_folium(
        map_view,
        key="area_map",
        height=480,
        use_container_width=True,
        returned_objects=["all_drawings"],
    )

    # None is the component's initial return. An empty list means the user
    # removed the drawing, so it must clear the selected geometry too.
    drawings = map_state.get("all_drawings") if map_state else None
    if drawings is not None:
        st.session_state.map_drawings = drawings
    drawings = st.session_state.get("map_drawings", [])
    if not drawings:
        return None, None
    if len(drawings) != 1:
        return None, "Keep one rectangle on the map. Use the trash tool to remove extra drawings."
    try:
        return rectangle_from_geojson(drawings[0]), None
    except LocationError as exc:
        return None, str(exc)


def coordinate_area() -> tuple[AnalysisArea | None, str | None]:
    st.write("Enter the rectangle edges in decimal degrees. West and east must stay on the same side of the 180° meridian.")
    first, second = st.columns(2)
    with first:
        north = st.number_input("North latitude", min_value=-90.0, max_value=90.0, value=SAMPLE_AREA.north, format="%.6f", step=0.0001)
        south = st.number_input("South latitude", min_value=-90.0, max_value=90.0, value=SAMPLE_AREA.south, format="%.6f", step=0.0001)
    with second:
        east = st.number_input("East longitude", min_value=-180.0, max_value=180.0, value=SAMPLE_AREA.east, format="%.6f", step=0.0001)
        west = st.number_input("West longitude", min_value=-180.0, max_value=180.0, value=SAMPLE_AREA.west, format="%.6f", step=0.0001)
    try:
        area = validate_rectangle(south, west, north, east)
    except LocationError as exc:
        return None, str(exc)
    preview_area(area)
    return area, None


def preview_area(area: AnalysisArea) -> None:
    preview = folium.Map(location=list(area.center), zoom_start=14, control_scale=True)
    folium.Rectangle(
        bounds=[[area.south, area.west], [area.north, area.east]],
        color="#15803d",
        fill=True,
        fill_opacity=0.16,
    ).add_to(preview)
    add_map_layers(preview)
    preview.fit_bounds([[area.south, area.west], [area.north, area.east]])
    st_folium(preview, key="area_preview", height=320, use_container_width=True, returned_objects=[])


def show_forecast(result: WeatherResult, request: AnalysisRequest) -> None:
    summary = compute_agro_climatic_summary(result)
    suitability_icons = {
        "Favorable": "🟢 Favorable",
        "Caution: Wet": "🟡 Caution: Wet",
        "Caution: Heat": "🟡 Caution: Heat",
        "Restricted: Rain": "🔴 Restricted: Rain",
        "Restricted: Heat": "🔴 Restricted: Heat",
    }

    hdr_col, unit_col = st.columns([3, 1])
    with hdr_col:
        st.subheader("Seven-day forecast & water balance")
    with unit_col:
        is_imperial = st.toggle("Imperial units (°F, in)", value=False)

    temp_unit = "°F" if is_imperial else "°C"
    len_unit = "in" if is_imperial else "mm"
    to_temp = lambda c: round(c * 9 / 5 + 32, 1) if is_imperial else round(c, 1)
    to_len = lambda mm: round(mm / 25.4, 2) if is_imperial else round(mm, 1)

    rows = [
        {
            "Date": row.day.isoformat(),
            f"Rain ({len_unit})": to_len(row.rain_mm),
            f"Max temp ({temp_unit})": to_temp(row.max_temp_c),
            f"Ref ET₀ ({len_unit})": to_len(row.et0_mm),
            f"Net P − ET₀ ({len_unit})": to_len(row.net_balance_mm),
            "Fieldwork window": suitability_icons.get(row.suitability, row.suitability),
        }
        for row in summary.days
    ]
    frame = pd.DataFrame(rows)
    latitude, longitude = result.area.center

    st.caption(
        f"Selected rectangle: {result.area.area_km2:.3f} km² · "
        f"Weather grid queried near its centre ({latitude:.5f}°, {longitude:.5f}°) · "
        f"Dates in {result.timezone}"
    )
    st.write(f"**Crop:** {request.crop}  |  **Growth stage:** {request.growth_stage}")
    st.caption("Crop and stage inform the checks below; they do not change this weather forecast.")
    a, b, c, d = st.columns(4)
    a.metric("Forecast rain", f"{to_len(summary.total_rain_mm)} {len_unit}", help="Sum of forecast daily rain; not measured rainfall.")
    b.metric("Highest daily max", f"{to_temp(max(day.max_temp_c for day in result.days))} {temp_unit}")
    c.metric("Reference ET₀ total", f"{to_len(summary.total_et0_mm)} {len_unit}", help="Reference evapotranspiration for a well-watered grass surface; not a crop irrigation prescription.")
    d.metric(
        f"Net water balance ({len_unit})",
        f"{to_len(summary.net_balance_mm):+0.2f if is_imperial else summary.net_balance_mm:+0.1f} {len_unit}",
        delta=summary.status_label,
        delta_color="normal" if summary.net_balance_mm >= 0 else "inverse",
        help="Cumulative precipitation minus reference ET₀. Atmospheric indicator of drying vs wetting trend.",
    )

    st.dataframe(frame, hide_index=True, width="stretch")
    left, right = st.columns(2)
    with left:
        st.markdown(f"**Daily rain vs reference ET₀ ({len_unit}/day)**")
        water_df = pd.DataFrame({
            "Date": [row.day.isoformat() for row in summary.days],
            f"Rain ({len_unit})": [to_len(row.rain_mm) for row in summary.days],
            f"Reference ET₀ ({len_unit})": [to_len(row.et0_mm) for row in summary.days],
        })
        st.bar_chart(water_df, x="Date", y=[f"Rain ({len_unit})", f"Reference ET₀ ({len_unit})"], height=260)
    with right:
        st.markdown(f"**Daily maximum temperature ({temp_unit})**")
        st.line_chart(frame, x="Date", y=f"Max temp ({temp_unit})", y_label=temp_unit, height=260)

    windows = evaluate_operational_windows(result)
    with st.expander("🚜 Field Operations Planner (7-day windows)", expanded=False):
        op1, op2, op3 = st.columns(3)
        op1.metric("🚜 Machinery Access", f"{len(windows.machinery_accessible_days)} / 7 days", help="Low soil saturation risk; minimal chance of field rutting.")
        op2.metric("🚿 Spraying Window", f"{len(windows.spraying_favorable_days)} / 7 days", help="Low droplet volatilization (<32°C) and minimal rain wash-off (<2mm).")
        op3.metric("🔍 Ground Scouting", f"{len(windows.scouting_recommended_days)} / 7 days", help="Favorable conditions for crop walks and visual inspection.")

    st.caption(
        f"Fetched {result.fetched_at_utc.strftime('%d %b %Y, %H:%M UTC')} from "
        "[Open-Meteo](https://open-meteo.com/en/docs). "
        "ET₀ is reference evapotranspiration, not a measured soil or crop water requirement."
    )


def show_satellite(result: SatelliteResult) -> None:
    st.subheader("Sentinel-2 vegetation observation")
    st.write(f"**Scene:** [{result.scene_id}]({result.catalog_url})")
    st.caption(
        f"Acquired {result.acquired_at_utc.strftime('%d %b %Y, %H:%M UTC')} · "
        f"Scene-wide cloud cover {result.scene_cloud_percent:.1f}% · "
        f"Read {result.width} × {result.height} pixels per 10 m band within the selected rectangle · "
        f"Fetched {result.fetched_at_utc.strftime('%d %b %Y, %H:%M UTC')}"
    )
    st.metric("Usable pixels in selected rectangle", f"{result.valid_pixel_percent:.1f}%")
    if result.quality_message:
        st.warning(result.quality_message)
    else:
        left_ndvi, right_ndvi = st.columns([2, 1])
        with left_ndvi:
            st.image(result.ndvi_png, caption="Cloud-masked NDVI · transparent = excluded", width="stretch")
            st.markdown(
                """
                <div style="margin-top: 4px; margin-bottom: 8px;">
                  <div style="display: flex; justify-content: space-between; font-size: 11px; color: #555;">
                    <span>−1.0 (Water)</span>
                    <span>0.0 (Soil)</span>
                    <span>+0.3 (Sparse)</span>
                    <span>+0.6 (Moderate)</span>
                    <span>+1.0 (Dense)</span>
                  </div>
                  <div style="height: 10px; width: 100%; border-radius: 4px; background: linear-gradient(to right, rgb(117,72,43), rgb(221,209,164) 50%, rgb(187,215,126) 65%, rgb(64,148,78) 80%, rgb(15,78,44) 100%);"></div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with right_ndvi:
            st.metric("Mean NDVI", f"{result.mean_ndvi:.3f}")
            st.metric("Median NDVI", f"{result.median_ndvi:.3f}")
            if result.mean_savi is not None:
                st.metric("Mean SAVI (Soil-Adjusted)", f"{result.mean_savi:.3f}", help="Soil-Adjusted Vegetation Index reduces bare-soil background distortion in sparse or emerging canopies.")
            st.caption("NDVI & SAVI describe greenness in this analysis rectangle. They cannot identify a disease, prove crop type, or measure yield.")

        if result.canopy_zones:
            st.markdown("**Vegetation Canopy Distribution**")
            zone_cols = st.columns(len(result.canopy_zones))
            zone_icons = ["🟩", "🟨", "🟧", "🟫", "🟦"]
            for col, (zone_name, pct), icon in zip(zone_cols, result.canopy_zones.items(), zone_icons):
                short_label = zone_name.split("(")[0].strip()
                col.metric(f"{icon} {short_label}", f"{pct:.1f}%")
    left, right = st.columns(2)
    with left:
        st.image(result.red_preview_png, caption="Red band (B04), contrast-enhanced preview", width="stretch")
    with right:
        st.image(result.nir_preview_png, caption="Near-infrared band (B08), contrast-enhanced preview", width="stretch")
    st.caption(
        "Source: [Element 84 Earth Search / Copernicus Sentinel-2 L2A](https://earth-search.aws.element84.com/v1). "
        "Red and NIR previews use a contrast stretch for viewing only. NDVI uses STAC reflectance scale and offset, "
        "with scene-classification masking of clouds, shadows, snow, uncertain pixels, and no-data. "
        "Clear water pixels are included if present; draw tightly around one field."
    )


def show_weather_state(state: SourceState, request: AnalysisRequest) -> None:
    if state.cached:
        st.info("Saved same-area forecast. Check its original dates and fetch time below; this is not a current forecast.")
    if state.error:
        st.warning(f"Live weather: {state.error}" if state.result else state.error)
    if isinstance(state.result, WeatherResult):
        show_forecast(state.result, request)


def show_satellite_state(state: SourceState) -> None:
    if state.cached:
        st.info("Saved same-area satellite result. The scene acquisition and fetch dates below are unchanged.")
    if state.error:
        st.warning(f"Live satellite: {state.error}" if state.result else state.error)
    if isinstance(state.result, SatelliteResult):
        show_satellite(state.result)


def show_suggestions(outcome: AnalysisOutcome) -> None:
    st.subheader("Checks to consider next")
    if not outcome.suggestions:
        st.info("No supported suggestion is available from the current results. Retry the live sources or choose another area.")
        return
    st.caption(outcome.suggestion_source + " · Decision support only; verify conditions on site.")
    for index, item in enumerate(outcome.suggestions, 1):
        st.markdown(f"**{index}. {item.candidate.title}**")
        st.write(item.candidate.action)
        st.caption("Evidence: " + " ".join(piece.text for piece in item.evidence))


def show_export_section(outcome: AnalysisOutcome) -> None:
    st.divider()
    st.subheader("Field advisory report export")
    st.caption("Download a complete, dated advisory report containing coordinates, crop stage, agro-climatic water balance, satellite vegetation metrics, and prioritized checks.")
    dl_left, dl_right = st.columns(2)
    crop_slug = outcome.request.crop.lower().replace(" ", "_") if outcome.request.crop else "field"
    center = outcome.request.area.center
    filename_base = f"cropscope_advisory_{crop_slug}_{center[0]:.2f}_{center[1]:.2f}"
    with dl_left:
        st.download_button(
            label="📥 Download Advisory Report (Markdown)",
            data=generate_advisory_markdown(outcome),
            file_name=f"{filename_base}.md",
            mime="text/markdown",
            use_container_width=True,
        )
    with dl_right:
        st.download_button(
            label="📥 Download Raw Analysis (JSON)",
            data=generate_advisory_json(outcome),
            file_name=f"{filename_base}.json",
            mime="application/json",
            use_container_width=True,
        )


st.set_page_config(page_title="CropScope", page_icon="🌱", layout="wide")
st.title("CropScope")
st.write("Select an agricultural area to see its forecast weather, a recent Sentinel-2 vegetation observation, and evidence-backed checks. The outlined rectangle is an analysis area, not a surveyed field boundary.")

mode = st.radio(
    "Choose the analysis area",
    ["Draw on map", "Enter coordinates", "Use sample preset"],
    horizontal=True,
)
if st.session_state.get("location_mode") != mode:
    st.session_state.location_mode = mode
    st.session_state.map_drawings = []
if mode == "Draw on map":
    area, location_error = draw_area()
elif mode == "Enter coordinates":
    area, location_error = coordinate_area()
else:
    preset_name = st.selectbox(
        "Select sample farmland location",
        list(SAMPLE_PRESETS.keys()),
        index=0,
        help="Pre-configured sample areas in India, Europe, and Australia.",
    )
    st.caption(f"Preset loaded: **{preset_name}**. You can also freely draw or enter coordinates anywhere.")
    area, location_error = SAMPLE_PRESETS[preset_name], None
    preview_area(area)

if location_error:
    st.warning(location_error)
elif area is None:
    st.info("Draw one rectangle to continue.")
else:
    latitude, longitude = area.center
    st.success(
        f"Selected area: {area.area_km2:.3f} km² · "
        f"South {area.south:.6f}°, West {area.west:.6f}°, "
        f"North {area.north:.6f}°, East {area.east:.6f}° "
        f"(centre {latitude:.5f}°, {longitude:.5f}°)."
    )

first, second = st.columns(2)
with first:
    crop = st.text_input("Crop", placeholder="e.g. wheat", max_chars=60).strip()
with second:
    growth_stage = st.selectbox(
        "Growth stage",
        ["Seedling", "Vegetative", "Flowering", "Fruit or grain filling", "Maturity", "Other or unknown"],
        index=None,
        placeholder="Select a stage",
    )

first_button, second_button = st.columns(2)
with first_button:
    analyze_live = st.button("Analyze / retry live", type="primary")
with second_button:
    use_saved = st.button("Use saved result for this rectangle")
current_request = AnalysisRequest(area, crop, growth_stage) if area and crop and growth_stage else None
if st.session_state.get("analysis_request") != current_request:
    st.session_state.pop("analysis_outcome", None)
    st.session_state.pop("analysis_request", None)

if analyze_live or use_saved:
    if area is None:
        st.error(location_error or "Select a valid rectangle before analyzing.")
    elif not crop or not growth_stage:
        st.error("Enter a crop and select its growth stage before analyzing.")
    else:
        st.session_state.analysis_request = current_request
        weather_slot, satellite_slot, suggestion_slot = st.empty(), st.empty(), st.empty()
        cache = CacheStore(Path(__file__).resolve().parent / "cache",
                           Path(__file__).resolve().parent / "sample_data")
        with st.status("Loading saved area data…" if use_saved else "Fetching live area data…", expanded=True) as progress:
            progress.write("Weather: loading saved result…" if use_saved else "Weather: requesting forecast…")
            def on_weather(state: SourceState) -> None:
                progress.write("Weather: saved result loaded." if state.cached else
                               "Weather: ready." if state.result else "Weather: unavailable.")
                with weather_slot.container():
                    show_weather_state(state, current_request)
                progress.write("Satellite: loading saved result…" if use_saved else
                               "Satellite: searching scenes, reading bands, and processing NDVI…")

            def on_satellite(state: SourceState) -> None:
                progress.write("Satellite: saved result loaded." if state.cached else
                               "Satellite: ready." if state.result else "Satellite: unavailable.")
                with satellite_slot.container():
                    show_satellite_state(state)

            outcome = run_analysis(current_request, cache, cached_only=use_saved,
                                   on_weather=on_weather, on_satellite=on_satellite)
            progress.write("Recommendations: validated AI ranking or rule-based fallback complete.")
            progress.update(label="Analysis complete", state="complete")
        st.session_state.analysis_outcome = outcome
        with suggestion_slot.container():
            show_suggestions(outcome)
            show_export_section(outcome)
elif st.session_state.get("analysis_outcome"):
    outcome = st.session_state.analysis_outcome
    show_weather_state(outcome.weather, outcome.request)
    show_satellite_state(outcome.satellite)
    show_suggestions(outcome)
    show_export_section(outcome)
