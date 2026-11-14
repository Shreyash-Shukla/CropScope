"""CropScope: selected-area weather and Sentinel-2 vegetation processing."""

import re
from pathlib import Path

import folium
import pandas as pd
import streamlit as st
from folium.plugins import Draw, Geocoder, LocateControl
from streamlit_folium import st_folium

from agronomy import (
    COMMON_CROPS,
    GROWTH_STAGE_GUIDANCE,
    compute_agro_climatic_summary,
    evaluate_operational_windows,
    generate_weather_alerts,
    get_growth_stage_guidance,
    summarize_canopy_health,
)
from analysis import AnalysisOutcome, SourceState, analyze as run_analysis
from cache import CacheStore
from globe import build_globe_html, is_location_sunlit
from location import (
    LocationError,
    SAMPLE_AREA,
    SAMPLE_PRESETS,
    area_from_coordinates,
    generate_area_geojson_str,
    get_ip_location,
    parse_coordinate_string,
    rectangle_from_geojson,
    search_locations,
    validate_rectangle,
)
from models import AnalysisArea, AnalysisRequest, SatelliteResult, WeatherResult
from reporting import advisory_filename_base, generate_advisory_json, generate_advisory_markdown


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
    st.write("Zoom to your location, choose the rectangle tool at the top left, and drag across one field. Use the layer icon (top right) to switch between Day/Night/Satellite maps. Use the crosshair icon to jump to your location. Use the trash tool to clear before drawing another.")
    map_view = folium.Map(location=[18, 0], zoom_start=2, control_scale=True, tiles=None)
    add_map_layers(map_view)
    Geocoder(collapsed=True).add_to(map_view)
    LocateControl(auto_start=False, flyTo=True, keepCurrentZoomLevel=False).add_to(map_view)
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


def search_location_area() -> tuple[AnalysisArea | None, str | None]:
    st.write("Search any town, agricultural region, landmark, or farm address worldwide.")
    col_search, col_extent = st.columns([3, 1])
    with col_search:
        search_query = st.text_input(
            "Search location",
            placeholder="e.g. Karnal, Beauce, Salinas Valley, Wagga Wagga, Foggia...",
            help="Type a place name, region, or city and press Enter.",
            key="location_search_input",
        )
    with col_extent:
        extent_choice = st.selectbox(
            "Field extent (side)",
            ["250 m (~6 ha)", "500 m (~25 ha)", "1.0 km (~100 ha)", "2.0 km (~400 ha)"],
            index=1,
            help="Select the analysis square size centered on the search target.",
            key="search_loc_extent_select",
        )
        side_km = {
            "250 m (~6 ha)": 0.25,
            "500 m (~25 ha)": 0.50,
            "1.0 km (~100 ha)": 1.00,
            "2.0 km (~400 ha)": 2.00,
        }.get(extent_choice, 0.50)

    if not search_query.strip():
        st.caption("Type any town, farm district, or landmark to retarget. Displaying default orbital preview:")
        preview_area(SAMPLE_AREA, location_title="Karnal Farmland, Haryana (Preset)")
        return SAMPLE_AREA, None

    try:
        results = search_locations(search_query)
    except LocationError as exc:
        return None, str(exc)

    if not results:
        return None, f"No locations found for '{search_query}'. Try a nearby town or broader region."

    labels = [f"{r['label']} ({r['latitude']:.4f}°, {r['longitude']:.4f}°)" for r in results]
    selected_idx = 0
    if len(labels) > 1:
        chosen_label = st.selectbox(
            "Multiple matching places found — select your target:",
            labels,
            index=0,
            key="search_match_select",
        )
        selected_idx = labels.index(chosen_label)

    match = results[selected_idx]
    lat, lon = match["latitude"], match["longitude"]
    st.success(f"📍 Selected: **{match['label']}** (`{lat:.5f}°, {lon:.5f}°`)")

    try:
        area = area_from_coordinates(lat, lon, side_km=side_km)
    except LocationError as exc:
        return None, str(exc)

    st.caption(f"Area extent: **{area.formatted_area()}**")
    preview_area(area, location_title=match["label"])
    return area, None


def coordinate_area() -> tuple[AnalysisArea | None, str | None]:
    st.write("Enter the latitude and longitude of your field or specify boundary edges.")
    coord_entry_type = st.radio(
        "Coordinate entry method",
        ["Center Point (Latitude & Longitude)", "Four-Corner Boundary (N/S/W/E)"],
        horizontal=True,
        key="coord_entry_type",
    )
    if coord_entry_type == "Center Point (Latitude & Longitude)":
        pasted = st.text_input(
            "Paste coordinates (optional quick-fill)",
            placeholder="e.g. 29.7495, 77.0502 or 48.25° N, 1.70° E",
            help="Type or paste latitude and longitude in any standard format and press Enter to auto-fill.",
            key="coord_paste_input",
        )
        default_lat, default_lon = SAMPLE_AREA.center
        if pasted.strip():
            try:
                parsed_lat, parsed_lon = parse_coordinate_string(pasted)
                default_lat, default_lon = parsed_lat, parsed_lon
            except LocationError as exc:
                st.caption(f":warning: {exc}")

        c1, c2, c3 = st.columns([2, 2, 2])
        with c1:
            lat = st.number_input(
                "Latitude",
                min_value=-90.0,
                max_value=90.0,
                value=float(default_lat),
                format="%.6f",
                step=0.0001,
                key="coord_center_lat",
            )
        with c2:
            lon = st.number_input(
                "Longitude",
                min_value=-180.0,
                max_value=180.0,
                value=float(default_lon),
                format="%.6f",
                step=0.0001,
                key="coord_center_lon",
            )
        with c3:
            extent_choice = st.selectbox(
                "Field extent (side)",
                ["250 m (~6 ha)", "500 m (~25 ha)", "1.0 km (~100 ha)", "2.0 km (~400 ha)"],
                index=1,
                help="CropScope analyzes a square field window centered on your coordinates (0.01 - 9.0 km²).",
                key="coord_extent_select",
            )
            side_km = {
                "250 m (~6 ha)": 0.25,
                "500 m (~25 ha)": 0.50,
                "1.0 km (~100 ha)": 1.00,
                "2.0 km (~400 ha)": 2.00,
            }.get(extent_choice, 0.50)

        try:
            area = area_from_coordinates(lat, lon, side_km=side_km)
        except LocationError as exc:
            return None, str(exc)

        st.caption(f"Area extent: **{area.formatted_area()}** (Center: {lat:.5f}°, {lon:.5f}°)")
        preview_area(area, location_title=f"Field ({lat:.4f}°, {lon:.4f}°)")
        return area, None
    else:
        st.write("Enter the rectangle edges in decimal degrees. West and east must stay on the same side of the 180° meridian.")
        first, second = st.columns(2)
        with first:
            north = st.number_input(
                "North latitude",
                min_value=-90.0,
                max_value=90.0,
                value=SAMPLE_AREA.north,
                format="%.6f",
                step=0.0001,
                key="coord_north",
            )
            south = st.number_input(
                "South latitude",
                min_value=-90.0,
                max_value=90.0,
                value=SAMPLE_AREA.south,
                format="%.6f",
                step=0.0001,
                key="coord_south",
            )
        with second:
            west = st.number_input(
                "West longitude",
                min_value=-180.0,
                max_value=180.0,
                value=SAMPLE_AREA.west,
                format="%.6f",
                step=0.0001,
                key="coord_west",
            )
            east = st.number_input(
                "East longitude",
                min_value=-180.0,
                max_value=180.0,
                value=SAMPLE_AREA.east,
                format="%.6f",
                step=0.0001,
                key="coord_east",
            )
        try:
            area = validate_rectangle(south, west, north, east)
        except LocationError as exc:
            return None, str(exc)
        st.caption(f"Area extent: **{area.formatted_area()}**")
        preview_area(area, location_title="Custom Coordinate Boundary")
        return area, None


def my_location_area() -> tuple[AnalysisArea | None, str | None]:
    st.write("Automatically detect your current field location using device GPS or network geolocation.")

    gps_lat_param = st.query_params.get("user_lat")
    gps_lon_param = st.query_params.get("user_lon")
    if gps_lat_param and gps_lon_param:
        try:
            st.session_state.my_location_coords = (float(gps_lat_param), float(gps_lon_param), "Device GPS Position")
        except ValueError:
            pass

    col_btn1, col_btn2 = st.columns([1, 1])
    with col_btn1:
        if st.button("🌐 Detect Network Location", use_container_width=True, help="Fast zero-prompt geolocation via network IP"):
            try:
                lat, lon, label = get_ip_location()
                st.session_state.my_location_coords = (lat, lon, label)
            except LocationError as exc:
                return None, str(exc)

    with col_btn2:
        st.components.v1.html(
            """
            <div style="display: flex; justify-content: center; align-items: center; height: 100%;">
              <button onclick="requestGps()" style="
                width: 100%;
                background: #ff6a1a;
                color: #07080a;
                border: 1px solid rgba(236, 232, 224, 0.22);
                border-radius: 0px;
                padding: 9px 16px;
                font-family: 'Martian Mono', ui-monospace, monospace;
                font-size: 11.5px;
                font-weight: 500;
                text-transform: uppercase;
                letter-spacing: 0.04em;
                cursor: pointer;
              ">📍 Use Device GPS</button>
            </div>
            <script>
              function requestGps() {
                if (navigator.geolocation) {
                  navigator.geolocation.getCurrentPosition(function(pos) {
                    const url = new URL(window.parent.location.href);
                    url.searchParams.set('user_lat', pos.coords.latitude.toFixed(6));
                    url.searchParams.set('user_lon', pos.coords.longitude.toFixed(6));
                    window.parent.location.href = url.href;
                  }, function(err) {
                    alert('GPS location error: ' + err.message);
                  }, { enableHighAccuracy: true, timeout: 10000 });
                } else {
                  alert('Geolocation is not supported by your browser.');
                }
              }
            </script>
            """,
            height=45,
        )

    coords_data = st.session_state.get("my_location_coords")
    if not coords_data:
        st.info("Click **'🌐 Detect Network Location'** or **'📍 Use Device GPS'** above to pinpoint your field.")
        preview_area(SAMPLE_AREA, location_title="Global Orbital Console (Locate Field Above)")
        return None, None

    lat, lon, label = coords_data
    st.success(f"📍 Selected Location: **{label}** (`{lat:.5f}°, {lon:.5f}°`)")

    extent_choice = st.selectbox(
        "Field extent around your location",
        ["250 m (~6 ha)", "500 m (~25 ha)", "1.0 km (~100 ha)", "2.0 km (~400 ha)"],
        index=1,
        help="Select the analysis window size surrounding your detected location.",
        key="my_loc_extent_select",
    )
    side_km = {
        "250 m (~6 ha)": 0.25,
        "500 m (~25 ha)": 0.50,
        "1.0 km (~100 ha)": 1.00,
        "2.0 km (~400 ha)": 2.00,
    }.get(extent_choice, 0.50)

    try:
        area = area_from_coordinates(lat, lon, side_km=side_km)
    except LocationError as exc:
        return None, str(exc)

    st.caption(f"Area extent: **{area.formatted_area()}**")
    preview_area(area, location_title=label)
    return area, None


def preview_area(area: AnalysisArea, location_title: str = "Selected Field") -> None:
    lat, lon = area.center
    is_day, elev = is_location_sunlit(lat, lon)
    sun_badge = "DAYLIGHT" if is_day else "NIGHT SHADOW"

    globe_html = build_globe_html(lat, lon, location_title, height=540)
    st.components.v1.html(globe_html, height=555)

    with st.expander("MAP / 2D High-Resolution Field Inspection Boundary", expanded=False):
        preview = folium.Map(location=list(area.center), zoom_start=14, control_scale=True, tiles=None)
        folium.Rectangle(
            bounds=[[area.south, area.west], [area.north, area.east]],
            color="#ff6a1a",
            fill=True,
            fill_opacity=0.18,
        ).add_to(preview)
        add_map_layers(preview)
        preview.fit_bounds([[area.south, area.west], [area.north, area.east]])
        preview_key = f"area_preview_{area.south:.4f}_{area.west:.4f}_{area.north:.4f}_{area.east:.4f}"
        st_folium(
            preview,
            key=preview_key,
            height=340,
            use_container_width=True,
            center=list(area.center),
            zoom=14,
            returned_objects=[],
        )


def show_forecast(result: WeatherResult, request: AnalysisRequest) -> None:
    summary = compute_agro_climatic_summary(result)
    suitability_icons = {
        "Favorable": "[FAVORABLE]",
        "Caution: Wet": "[CAUTION: WET]",
        "Caution: Heat": "[CAUTION: HEAT]",
        "Restricted: Rain": "[RESTRICTED: RAIN]",
        "Restricted: Heat": "[RESTRICTED: HEAT]",
    }

    hdr_col, unit_col = st.columns([3, 1])
    with hdr_col:
        st.markdown(
            """
            <div style="font-family: var(--font-mono); font-size: 10px; color: var(--bone-3); text-transform: uppercase; letter-spacing: 0.08em; margin-bottom: 4px;">
              03 / AGRO-CLIMATIC WATER BALANCE
            </div>
            <div style="font-family: var(--font-sans); font-size: 24px; font-weight: 500; color: var(--bone); line-height: 1.1; margin-bottom: 8px;">
              Seven-day forecast & water balance
            </div>
            """,
            unsafe_allow_html=True,
        )
    with unit_col:
        is_imperial = st.toggle("Imperial units (°F, in)", value=False, key="is_imperial_units")

    alerts = generate_weather_alerts(result)
    for alert in alerts:
        if alert.level == "danger":
            st.error(alert.message)
        elif alert.level == "warning":
            st.warning(alert.message)
        elif alert.level == "success":
            st.success(alert.message)
        else:
            st.info(alert.message)

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
            "Advisory note": row.reason,
        }
        for row in summary.days
    ]
    frame = pd.DataFrame(rows)
    latitude, longitude = result.area.center

    st.caption(
        f"Selected rectangle: {result.area.formatted_area()} · "
        f"Weather grid queried near its centre ({latitude:.5f}°, {longitude:.5f}°) · "
        f"Dates in {result.timezone}"
    )
    st.write(f"**Crop:** {request.crop}  |  **Growth stage:** {request.growth_stage}")
    st.caption("Crop and stage inform the checks below; they do not change this weather forecast.")
    a, b, c, d = st.columns(4)
    highest_heat = max(result.days, key=lambda day: day.max_temp_c)
    a.metric("Forecast rain", f"{to_len(summary.total_rain_mm)} {len_unit}", help="Sum of forecast daily rain; not measured rainfall.")
    b.metric("Highest daily max", f"{to_temp(highest_heat.max_temp_c)} {temp_unit}", delta=f"{highest_heat.day.strftime('%a, %d %b')}", delta_color="off", help="Peak forecast maximum temperature this week.")
    c.metric("Reference ET₀ total", f"{to_len(summary.total_et0_mm)} {len_unit}", help="Reference evapotranspiration for a well-watered grass surface; not a crop irrigation prescription.")
    status_short = (
        "Surplus" if summary.net_balance_mm >= 15.0
        else "Deficit" if summary.net_balance_mm <= -15.0
        else "Near-neutral"
    )
    formatted_balance = (
        f"{to_len(summary.net_balance_mm):+0.2f}"
        if is_imperial
        else f"{summary.net_balance_mm:+0.1f}"
    )
    d.metric(
        f"Net water balance ({len_unit})",
        f"{formatted_balance} {len_unit}",
        delta=status_short,
        delta_color="normal" if summary.net_balance_mm >= 0 else "inverse",
        help=f"Cumulative precipitation minus reference ET₀: {summary.status_label}. Atmospheric indicator of drying vs wetting trend.",
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
    with st.expander("🚜 Field Operations Planner (7-day operational windows)", expanded=False):
        op1, op2, op3 = st.columns(3)
        op1.metric("🚜 Machinery Access", f"{len(windows.machinery_accessible_days)} / 7 days", help="Low soil saturation risk; minimal chance of field rutting.")
        op2.metric("🚿 Spraying Window", f"{len(windows.spraying_favorable_days)} / 7 days", help="Low droplet volatilization (<32°C) and minimal rain wash-off (<2mm).")
        op3.metric("🔍 Ground Scouting", f"{len(windows.scouting_recommended_days)} / 7 days", help="Favorable conditions for crop walks and visual inspection.")
        st.divider()
        format_days = lambda days: ", ".join(d.strftime("%a %d %b") for d in days) if days else "No favorable window forecast this week"
        st.markdown(f"**🚜 Machinery accessible days:** {format_days(windows.machinery_accessible_days)}")
        st.markdown(f"**🚿 Spraying favorable days:** {format_days(windows.spraying_favorable_days)}")
        st.markdown(f"**🔍 Recommended scouting days:** {format_days(windows.scouting_recommended_days)}")

    st.caption(
        f"Fetched {result.fetched_at_utc.strftime('%d %b %Y, %H:%M UTC')} from "
        "[Open-Meteo](https://open-meteo.com/en/docs). "
        "ET₀ is reference evapotranspiration, not a measured soil or crop water requirement."
    )


def show_satellite(result: SatelliteResult) -> None:
    st.markdown(
        f"""
        <div style="margin-top: 20px; margin-bottom: 18px; border-top: 1px solid var(--line); padding-top: 20px;">
          <div style="font-family: var(--font-mono); font-size: 10px; color: var(--bone-3); text-transform: uppercase; letter-spacing: 0.08em; margin-bottom: 6px;">
            02 / SATELLITE PASS ACQUISITION
          </div>
          <div style="font-family: var(--font-sans); font-size: 28px; font-weight: 500; color: var(--bone); line-height: 1.05; letter-spacing: -0.02em;">
            In the last 7 days, <span style="font-family: var(--font-serif); font-style: italic; color: var(--signal);">Sentinel-2 watched</span> this field.
          </div>
          <div style="font-family: var(--font-mono); font-size: 11px; color: var(--bone-2); margin-top: 6px; letter-spacing: 0.04em;">
            Scene <code>{result.scene_id}</code> · Acquired {result.acquired_at_utc.strftime('%Y-%m-%d %H:%M:%S UTC')} · Cloud cover: {result.scene_cloud_percent:.1f}% · 10m Ground Resolution
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if result.quality_message:
        st.warning(result.quality_message)
        st.metric("Usable pixels in selected rectangle", f"{result.valid_pixel_percent:.1f}%")
    else:
        left_ndvi, right_ndvi = st.columns([2, 1])
        with left_ndvi:
            st.image(result.ndvi_png, caption="Cloud-masked NDVI · transparent = excluded", width="stretch")
            st.markdown(
                """
                <div style="margin-top: 4px; margin-bottom: 8px;">
                  <div style="display: flex; justify-content: space-between; font-size: 11px; opacity: 0.85; font-weight: 500;">
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
            st.metric("Usable pixels in area", f"{result.valid_pixel_percent:.1f}%", help="Percentage of pixels in the analysis rectangle free from cloud, shadow, snow, or defective data.")
            st.metric("Mean NDVI", f"{result.mean_ndvi:.3f}")
            st.metric("Median NDVI", f"{result.median_ndvi:.3f}")
            if result.mean_savi is not None:
                st.metric("Mean SAVI (Soil-Adjusted)", f"{result.mean_savi:.3f}", help="Soil-Adjusted Vegetation Index reduces bare-soil background distortion in sparse or emerging canopies.")
            st.caption("NDVI & SAVI describe greenness in this analysis rectangle. They cannot identify a disease, prove crop type, or measure yield.")

        if result.canopy_zones:
            st.markdown("**Vegetation Canopy Distribution**")
            zone_meta = [
                ("Dense", "■", "#15803d", "Dense Canopy (NDVI > 0.60)"),
                ("Moderate", "■", "#84cc16", "Moderate Canopy (NDVI 0.35 - 0.60)"),
                ("Sparse", "■", "#eab308", "Sparse / Emerging (NDVI 0.20 - 0.35)"),
                ("Bare Soil", "■", "#a16207", "Bare Soil / Non-Vegetated (NDVI 0.00 - 0.20)"),
                ("Water / Neg", "■", "#0284c7", "Water / Negative Index (NDVI < 0.00)"),
            ]
            segments_html = []
            for (zone_name, pct), (short_name, icon, color, tooltip) in zip(result.canopy_zones.items(), zone_meta):
                if pct > 0:
                    segments_html.append(
                        f'<div style="width: {pct:.1f}%; background-color: {color}; height: 14px; '
                        f'display: inline-block;" title="{short_name}: {pct:.1f}%"></div>'
                    )
            if segments_html:
                st.markdown(
                    f'<div style="width: 100%; display: flex; border-radius: 4px; overflow: hidden; margin-bottom: 8px; border: 1px solid rgba(128,128,128,0.2);">'
                    f'{"".join(segments_html)}</div>',
                    unsafe_allow_html=True,
                )

            zone_cols = st.columns(len(result.canopy_zones))
            for col, (zone_name, pct), (short_name, icon, color, tooltip) in zip(zone_cols, result.canopy_zones.items(), zone_meta):
                col.metric(f"{icon} {short_name}", f"{pct:.1f}%", help=tooltip)

            summary_text = summarize_canopy_health(result.canopy_zones)
            if summary_text:
                st.caption(f"💡 {summary_text}")
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
    st.markdown(
        """
        <div style="margin-top: 24px; margin-bottom: 14px; border-top: 1px solid var(--line); padding-top: 18px;">
          <div style="font-family: var(--font-mono); font-size: 10px; color: var(--bone-3); text-transform: uppercase; letter-spacing: 0.08em; margin-bottom: 4px;">
            04 / FIELD ACTION CHECKS
          </div>
          <div style="font-family: var(--font-sans); font-size: 24px; font-weight: 500; color: var(--bone); line-height: 1.1;">
            Prioritized agronomic checks
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if not outcome.suggestions:
        st.info("No supported suggestion is available from the current results. Retry the live sources or choose another area.")
        return
    st.caption(outcome.suggestion_source + " · Decision support only; verify conditions on site.")
    for index, item in enumerate(outcome.suggestions, 1):
        st.markdown(f"**{index}. {item.candidate.title}**")
        st.write(item.candidate.action)
        st.caption("Evidence: " + " ".join(piece.text for piece in item.evidence))


def show_export_section(outcome: AnalysisOutcome) -> None:
    st.markdown(
        """
        <div style="margin-top: 24px; margin-bottom: 14px; border-top: 1px solid var(--line); padding-top: 18px;">
          <div style="font-family: var(--font-mono); font-size: 10px; color: var(--bone-3); text-transform: uppercase; letter-spacing: 0.08em; margin-bottom: 4px;">
            05 / EXPORT & GIS BOUNDARY
          </div>
          <div style="font-family: var(--font-sans); font-size: 24px; font-weight: 500; color: var(--bone); line-height: 1.1;">
            Field advisory report & GIS boundary export
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.caption("Download a complete, dated advisory report containing coordinates, crop stage, agro-climatic water balance, satellite vegetation metrics, prioritized checks, or the GIS field boundary.")
    dl_left, dl_mid, dl_right = st.columns(3)
    filename_base = advisory_filename_base(outcome)
    with dl_left:
        st.download_button(
            label="Advisory Report (Markdown)",
            data=generate_advisory_markdown(outcome),
            file_name=f"{filename_base}.md",
            mime="text/markdown",
            use_container_width=True,
        )
    with dl_mid:
        st.download_button(
            label="Raw Analysis (JSON)",
            data=generate_advisory_json(outcome),
            file_name=f"{filename_base}.json",
            mime="application/json",
            use_container_width=True,
        )
    with dl_right:
        st.download_button(
            label="Field Boundary (GeoJSON)",
            data=generate_area_geojson_str(outcome.request.area, f"{outcome.request.crop} Field Boundary"),
            file_name=f"{filename_base}_boundary.geojson",
            mime="application/geo+json",
            use_container_width=True,
        )


st.set_page_config(
    page_title="CropScope · Watched",
    page_icon="🛰️",
    layout="wide",
)

st.markdown(
    """
    <style>
      @import url('https://fonts.googleapis.com/css2?family=Instrument+Sans:ital,wght@0,400..700;1,400..700&family=Instrument+Serif:ital@0;1&family=Martian+Mono:wght@300;400;500;600&display=swap');

      :root {
        --ink-0: #07080a;
        --ink-1: #0c0e11;
        --ink-2: #14171c;
        --bone: #ece8e0;
        --bone-2: rgba(236, 232, 224, 0.64);
        --bone-3: rgba(236, 232, 224, 0.52);
        --bone-4: rgba(236, 232, 224, 0.18);
        --line: rgba(236, 232, 224, 0.10);
        --line-strong: rgba(236, 232, 224, 0.22);
        --signal: #ff6a1a;
        --signal-hover: #ff8340;
        --font-sans: 'Instrument Sans', -apple-system, BlinkMacSystemFont, sans-serif;
        --font-mono: 'Martian Mono', ui-monospace, monospace;
        --font-serif: 'Instrument Serif', Georgia, serif;
      }

      /* ── Watched.earth Hard Rules (DESIGN §1) ── */
      /* Pure ink background & bone typography */
      .stApp {
        background-color: var(--ink-0) !important;
        color: var(--bone) !important;
        font-family: var(--font-sans) !important;
      }

      /* Anti-slop: zero border radius everywhere */
      *, *::before, *::after {
        border-radius: 0px !important;
      }

      /* Streamlit Header & Navigation Chrome */
      header[data-testid="stHeader"] {
        background: var(--ink-0) !important;
        border-bottom: 1px solid var(--line) !important;
      }
      .main .block-container {
        padding-top: 1.5rem !important;
        padding-bottom: 3.5rem !important;
        max-width: 1280px !important;
      }

      /* Typography */
      h1, h2, h3, h4, h5, h6 {
        font-family: var(--font-sans) !important;
        color: var(--bone) !important;
        font-weight: 500 !important;
        letter-spacing: -0.02em !important;
      }
      p, span, label, div {
        color: var(--bone) !important;
      }
      small, .stCaption {
        font-family: var(--font-mono) !important;
        font-size: 11px !important;
        color: var(--bone-3) !important;
        letter-spacing: 0.04em !important;
      }

      /* Buttons: Sharp, flat ink or signal orange */
      button[kind="primary"], .stButton > button[kind="primary"] {
        background-color: var(--signal) !important;
        color: var(--ink-0) !important;
        font-family: var(--font-mono) !important;
        font-size: 11px !important;
        font-weight: 600 !important;
        letter-spacing: 0.08em !important;
        text-transform: uppercase !important;
        border: 1px solid var(--signal) !important;
        padding: 10px 18px !important;
        box-shadow: none !important;
        transition: background 120ms ease !important;
      }
      button[kind="primary"]:hover {
        background-color: var(--signal-hover) !important;
      }
      button[kind="secondary"], .stButton > button {
        background-color: var(--ink-1) !important;
        color: var(--bone) !important;
        font-family: var(--font-mono) !important;
        font-size: 11px !important;
        letter-spacing: 0.08em !important;
        text-transform: uppercase !important;
        border: 1px solid var(--line-strong) !important;
        padding: 10px 18px !important;
        box-shadow: none !important;
        transition: all 120ms ease !important;
      }
      button[kind="secondary"]:hover, .stButton > button:hover {
        background-color: var(--ink-2) !important;
        border-color: var(--bone-2) !important;
        color: #ffffff !important;
      }

      /* Inputs: Flat ink-1 with hairline borders */
      input, textarea, select, div[data-baseweb="input"], div[data-baseweb="select"] > div {
        background-color: var(--ink-1) !important;
        color: var(--bone) !important;
        border: 1px solid var(--line-strong) !important;
        font-family: var(--font-mono) !important;
        font-size: 12px !important;
        box-shadow: none !important;
      }
      input:focus, div[data-baseweb="input"]:focus-within {
        border-color: var(--signal) !important;
      }

      /* Metrics / Readouts */
      div[data-testid="stMetric"] {
        background-color: var(--ink-1) !important;
        border: 1px solid var(--line) !important;
        padding: 14px 16px !important;
        box-shadow: none !important;
      }
      div[data-testid="stMetricLabel"] p {
        font-family: var(--font-mono) !important;
        font-size: 10px !important;
        text-transform: uppercase !important;
        letter-spacing: 0.08em !important;
        color: var(--bone-3) !important;
      }
      div[data-testid="stMetricValue"] div {
        font-family: var(--font-mono) !important;
        font-size: 20px !important;
        font-variant-numeric: tabular-nums !important;
        color: var(--bone) !important;
      }

      /* Radio Navigation */
      div[data-testid="stRadio"] label {
        font-family: var(--font-mono) !important;
        font-size: 11px !important;
        letter-spacing: 0.06em !important;
        text-transform: uppercase !important;
      }

      /* Expanders */
      div[data-testid="stExpander"] {
        background-color: var(--ink-1) !important;
        border: 1px solid var(--line) !important;
      }

      /* Dataframes / Tables */
      div[data-testid="stDataFrame"] {
        border: 1px solid var(--line) !important;
      }

      /* Watched.earth Hero Section */
      .hero-container {
        margin-bottom: 24px;
        padding-bottom: 20px;
        border-bottom: 1px solid var(--line);
      }
      .hero-kicker {
        font-family: var(--font-mono);
        font-size: 10.5px;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        color: var(--bone-3);
        margin-bottom: 10px;
        display: flex;
        align-items: center;
        gap: 8px;
      }
      .hero-kicker-dot {
        width: 6px;
        height: 6px;
        background: var(--signal);
        display: inline-block;
      }
      .hero-title {
        font-family: var(--font-sans);
        font-size: clamp(34px, 4.6vw, 60px);
        font-weight: 520;
        line-height: 0.94;
        letter-spacing: -0.02em;
        color: var(--bone);
        margin: 0 0 12px 0;
      }
      .hero-serif {
        font-family: var(--font-serif);
        font-style: italic;
        font-weight: 400;
        color: var(--signal);
        font-size: 1.05em;
      }
      .hero-sub {
        font-family: var(--font-sans);
        font-size: 15px;
        color: var(--bone-2);
        max-width: 640px;
        line-height: 1.45;
        margin: 0;
      }
    </style>
    <div class="hero-container">
      <div class="hero-kicker"><span class="hero-kicker-dot"></span> 01 / ORBITAL SENSING CONSOLE · SGP4 CELESTRAK</div>
      <div class="hero-title">Something watched <span class="hero-serif">your crops</span> this week.</div>
      <div class="hero-sub">Enter any field or farm location on Earth. See every Sentinel-2 multispectral pass, NDVI canopy health, and 7-day agro-climatic water balance.</div>
    </div>
    """,
    unsafe_allow_html=True,
)

mode = st.radio(
    "Choose the analysis area",
    ["Search location", "Enter coordinates", "Use my location", "Draw on map", "Use sample preset"],
    horizontal=True,
)
if st.session_state.get("location_mode") != mode:
    st.session_state.location_mode = mode
    st.session_state.map_drawings = []
if mode == "Search location":
    area, location_error = search_location_area()
elif mode == "Enter coordinates":
    area, location_error = coordinate_area()
elif mode == "Use my location":
    area, location_error = my_location_area()
elif mode == "Draw on map":
    area, location_error = draw_area()
else:
    preset_name = st.selectbox(
        "Select sample farmland location",
        list(SAMPLE_PRESETS.keys()),
        index=0,
        help="Pre-configured sample areas in India, Europe, and Australia.",
    )
    st.caption(f"Preset loaded: **{preset_name}**. You can also freely draw or enter coordinates anywhere.")
    area, location_error = SAMPLE_PRESETS[preset_name], None
    preview_area(area, location_title=preset_name)

if location_error:
    st.warning(location_error)
elif area is None:
    st.info("Draw one rectangle to continue.")
else:
    latitude, longitude = area.center
    st.success(
        f"Selected area: {area.formatted_area()} · "
        f"South {area.south:.6f}°, West {area.west:.6f}°, "
        f"North {area.north:.6f}°, East {area.east:.6f}° "
        f"(centre {latitude:.5f}°, {longitude:.5f}°)."
    )
    with st.expander("COORDINATES / Bounding Box & GIS Geometry", expanded=False):
        c1, c2 = st.columns([2, 1])
        with c1:
            st.code(
                f"Bounding Box: [West: {area.west:.6f}, South: {area.south:.6f}, East: {area.east:.6f}, North: {area.north:.6f}]\n"
                f"Center: [{latitude:.6f}, {longitude:.6f}] | Size: {area.formatted_area()}",
                language="yaml",
            )
        with c2:
            st.download_button(
                "Export Field Boundary (GeoJSON)",
                data=generate_area_geojson_str(area, "Field Boundary"),
                file_name="crop_field_boundary.geojson",
                mime="application/geo+json",
                use_container_width=True,
            )

first, second = st.columns(2)
with first:
    crop_options = ["Select a crop...", *COMMON_CROPS, "Custom / Other..."]
    crop_selection = st.selectbox(
        "Crop",
        crop_options,
        index=0,
        key="crop_select",
        help="Select a common crop or choose 'Custom / Other...' to type any crop name.",
    )
    if crop_selection == "Custom / Other...":
        crop = st.text_input("Custom crop name", placeholder="e.g. sunflower, tomato", max_chars=60, key="custom_crop_input").strip()
    elif crop_selection != "Select a crop...":
        crop = crop_selection
    else:
        crop = ""
with second:
    growth_stage = st.selectbox(
        "Growth stage",
        list(GROWTH_STAGE_GUIDANCE.keys()),
        index=None,
        placeholder="Select a stage",
        key="growth_stage_select",
        help="Growth stage informs field checks, water sensitivity, and operational advisories.",
    )
    if growth_stage:
        st.caption(f"GUIDANCE: {get_growth_stage_guidance(growth_stage)}")

first_button, second_button = st.columns(2)
with first_button:
    analyze_live = st.button("ANALYZE SATELLITE PASSES →", type="primary", use_container_width=True)
with second_button:
    use_saved = st.button("USE SAVED ARCHIVE SCENE", use_container_width=True)

current_request = AnalysisRequest(area, crop, growth_stage) if area and crop and growth_stage else None
last_request = st.session_state.get("analysis_request")
if last_request and area and last_request.area != area:
    st.session_state.pop("analysis_outcome", None)
    st.session_state.pop("analysis_request", None)

if analyze_live or use_saved:
    if area is None:
        st.error(location_error or "Select a valid rectangle before analyzing.")
    elif not crop or not growth_stage:
        st.error("Enter a crop and select its growth stage before analyzing.")
    else:
        st.session_state.analysis_request = current_request
        cache = CacheStore(Path(__file__).resolve().parent / "cache",
                           Path(__file__).resolve().parent / "sample_data")
        status_container = st.container()
        weather_slot, satellite_slot, suggestion_slot = st.empty(), st.empty(), st.empty()
        with status_container:
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
    if current_request and (outcome.request.crop != current_request.crop or outcome.request.growth_stage != current_request.growth_stage):
        st.info("ℹ️ Inputs have changed. Click 'Analyze / retry live' or 'Use saved result' to update your advisory.")
    show_weather_state(outcome.weather, outcome.request)
    show_satellite_state(outcome.satellite)
    show_suggestions(outcome)
    show_export_section(outcome)
