"""CropScope: selected-area weather and Phase 2 satellite acquisition."""

import folium
import pandas as pd
import streamlit as st
from folium.plugins import Draw, Geocoder
from streamlit_folium import st_folium

from location import LocationError, SAMPLE_AREA, rectangle_from_geojson, validate_rectangle
from models import AnalysisArea, AnalysisRequest, SatelliteResult, WeatherResult
from satellite import NoSceneError, SatelliteError, fetch_satellite
from weather import WeatherError, fetch_weather


def draw_area() -> tuple[AnalysisArea | None, str | None]:
    st.write("Zoom to your location, choose the rectangle tool at the top left, and drag across one field. Use the trash tool to clear it before drawing another.")
    map_view = folium.Map(location=[18, 0], zoom_start=2, control_scale=True)
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
    preview.fit_bounds([[area.south, area.west], [area.north, area.east]])
    st_folium(preview, key="area_preview", height=320, use_container_width=True, returned_objects=[])


def show_forecast(result: WeatherResult, request: AnalysisRequest) -> None:
    rows = [
        {
            "Date": day.day.isoformat(),
            "Rain (mm)": day.rain_mm,
            "Max temperature (°C)": day.max_temp_c,
            "Reference ET₀ (mm)": day.et0_mm,
        }
        for day in result.days
    ]
    frame = pd.DataFrame(rows)
    latitude, longitude = result.area.center

    st.subheader("Seven-day forecast")
    st.caption(
        f"Selected rectangle: {result.area.area_km2:.3f} km² · "
        f"Weather grid queried near its centre ({latitude:.5f}°, {longitude:.5f}°) · "
        f"Dates in {result.timezone}"
    )
    st.write(f"**Crop:** {request.crop}  |  **Growth stage:** {request.growth_stage}")
    st.caption("Crop and stage are recorded for later recommendation features; they do not change this weather forecast.")
    a, b, c = st.columns(3)
    a.metric("Forecast rain", f"{sum(day.rain_mm for day in result.days):.1f} mm", help="Sum of forecast daily rain; not measured rainfall.")
    b.metric("Highest daily maximum", f"{max(day.max_temp_c for day in result.days):.1f} °C")
    c.metric("Reference ET₀ total", f"{sum(day.et0_mm for day in result.days):.1f} mm", help="Reference evapotranspiration for a well-watered grass surface; not a crop irrigation prescription.")

    st.dataframe(frame, hide_index=True, width="stretch")
    left, right = st.columns(2)
    with left:
        st.markdown("**Forecast rain (mm/day)**")
        st.bar_chart(frame, x="Date", y="Rain (mm)", y_label="mm", height=260)
    with right:
        st.markdown("**Daily maximum temperature (°C)**")
        st.line_chart(frame, x="Date", y="Max temperature (°C)", y_label="°C", height=260)

    st.caption(
        f"Fetched {result.fetched_at_utc.strftime('%d %b %Y, %H:%M UTC')} from "
        "[Open-Meteo](https://open-meteo.com/en/docs). "
        "ET₀ is reference evapotranspiration, not a measured soil or crop water requirement."
    )


def show_satellite(result: SatelliteResult) -> None:
    st.subheader("Sentinel-2 image acquisition")
    st.write(f"**Scene:** [{result.scene_id}]({result.catalog_url})")
    st.caption(
        f"Acquired {result.acquired_at_utc.strftime('%d %b %Y, %H:%M UTC')} · "
        f"Scene-wide cloud cover {result.scene_cloud_percent:.1f}% · "
        f"Read {result.width} × {result.height} pixels per 10 m band within the selected rectangle · "
        f"Fetched {result.fetched_at_utc.strftime('%d %b %Y, %H:%M UTC')}"
    )
    left, right = st.columns(2)
    with left:
        st.image(result.red_preview_png, caption="Red band (B04), contrast-enhanced preview", width="stretch")
    with right:
        st.image(result.nir_preview_png, caption="Near-infrared band (B08), contrast-enhanced preview", width="stretch")
    st.caption(
        "Source: [Element 84 Earth Search / Copernicus Sentinel-2 L2A](https://earth-search.aws.element84.com/v1). "
        "The contrast stretch is for viewing only. Scene-wide cloud cover does not describe cloud cover in this rectangle. "
        "Cloud masking, reflectance, and NDVI are planned for Phase 3."
    )


st.set_page_config(page_title="CropScope", page_icon="🌱", layout="wide")
st.title("CropScope")
st.write("Select an agricultural area to see its forecast weather and recent Sentinel-2 band previews. The outlined rectangle is an analysis area, not a surveyed field boundary.")

mode = st.radio(
    "Choose the analysis area",
    ["Draw on map", "Enter coordinates", "Use Karnal example"],
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
    st.write("Saved example near Karnal, Haryana. You can instead draw or enter a rectangle anywhere supported by the weather service.")
    area, location_error = SAMPLE_AREA, None
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

analyze = st.button("Analyze", type="primary")
current_request = AnalysisRequest(area, crop, growth_stage) if area and crop and growth_stage else None
if st.session_state.get("analysis_request") != current_request:
    st.session_state.pop("weather_result", None)
    st.session_state.pop("weather_error", None)
    st.session_state.pop("satellite_result", None)
    st.session_state.pop("satellite_error", None)
    st.session_state.pop("analysis_request", None)

if analyze:
    if area is None:
        st.error(location_error or "Select a valid rectangle before analyzing.")
    elif not crop or not growth_stage:
        st.error("Enter a crop and select its growth stage before analyzing.")
    else:
        st.session_state.analysis_request = current_request
        with st.spinner("Fetching weather for the selected area…"):
            try:
                st.session_state.weather_result = fetch_weather(area)
                st.session_state.weather_error = None
            except WeatherError as exc:
                st.session_state.weather_result = None
                st.session_state.weather_error = str(exc)
        with st.spinner("Searching recent Sentinel-2 scenes and reading band windows…"):
            try:
                st.session_state.satellite_result = fetch_satellite(area)
                st.session_state.satellite_error = None
            except (SatelliteError, NoSceneError) as exc:
                st.session_state.satellite_result = None
                st.session_state.satellite_error = str(exc)

if st.session_state.get("weather_error"):
    st.error(st.session_state.weather_error)
    st.caption("You can press Analyze again to retry. The selected area is retained.")
elif st.session_state.get("weather_result"):
    show_forecast(st.session_state.weather_result, st.session_state.analysis_request)

if st.session_state.get("satellite_error"):
    st.warning(st.session_state.satellite_error)
    st.caption("Weather results remain available above if the forecast succeeded. Press Analyze to retry the satellite search.")
elif st.session_state.get("satellite_result"):
    show_satellite(st.session_state.satellite_result)
