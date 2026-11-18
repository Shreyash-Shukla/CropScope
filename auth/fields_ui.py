"""UI widgets for Farmer Saved Fields management in CropScope.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import streamlit as st

from auth.session import get_active_field, get_current_farmer, set_active_field
from db.fields import list_fields, save_field
from models import AnalysisArea


def render_farmer_fields_selector(farmer_id: str, current_lang: str) -> Optional[AnalysisArea]:
    """Render saved field selector for logged in farmer.
    
    Returns AnalysisArea if a saved field is chosen, else None.
    """
    fields = list_fields(farmer_id)
    if not fields:
        return None

    field_options = ["-- Choose from My Fields (मेरे सहेजे गए खेत) --"] + [
        f"🌾 {f['name']} ({f['area_ha']:.1f} ha · {f['area_acres']:.1f} ac)" for f in fields
    ]

    selected_option = st.selectbox(
        "📍 My Farm Parcels / मेरे खेत",
        options=field_options,
        index=0,
        key="farmer_field_selector",
        help="Quickly load your previously saved farm parcels and boundaries.",
    )

    if selected_option != field_options[0]:
        idx = field_options.index(selected_option) - 1
        chosen_field = fields[idx]
        set_active_field(chosen_field)
        return AnalysisArea(
            south=chosen_field["bbox_south"],
            west=chosen_field["bbox_west"],
            north=chosen_field["bbox_north"],
            east=chosen_field["bbox_east"],
        )

    return None


def render_save_field_widget(farmer_id: str, area: AnalysisArea, current_lang: str) -> None:
    """Render field saving drawer when farmer is logged in and viewing an area."""
    with st.expander("💾 Save this Field to My Profile / यह खेत अपने खाते में सहेजें", expanded=False):
        c_name, c_soil, c_irrig = st.columns(3)
        with c_name:
            field_name = st.text_input(
                "Field Name / खेत का नाम *",
                placeholder="e.g. खेत 1 - नहर वाला",
                key="input_save_field_name",
            )
        with c_soil:
            soil_type = st.text_input(
                "Soil Type (Optional)",
                placeholder="e.g. Loam / Alluvial",
                key="input_save_soil_type",
            )
        with c_irrig:
            irrigation = st.selectbox(
                "Irrigation Source",
                ["Canal / नहर", "Tube Well / बोरवेल", "Rainfed / वर्षा आधारित", "Drip/Sprinkler", "Other"],
                key="select_save_irrigation",
            )

        if st.button("Save Field / खेत सहेजें", key="btn_do_save_field", type="primary", use_container_width=True):
            if not field_name.strip():
                st.error("Please enter a name for your field.")
            else:
                try:
                    new_field = save_field(
                        farmer_id=farmer_id,
                        name=field_name.strip(),
                        bbox=(area.south, area.west, area.north, area.east),
                        area_ha=area.area_ha,
                        soil_type=soil_type.strip() if soil_type else None,
                        irrigation_source=irrigation,
                    )
                    set_active_field(new_field)
                    st.success(f"Field '{field_name}' successfully saved to your profile!")
                    try:
                        st.rerun()
                    except Exception:
                        pass
                except Exception as exc:
                    st.error(f"Failed to save field: {exc}")
