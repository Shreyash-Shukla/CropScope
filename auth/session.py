"""Farmer authentication and session management in Streamlit.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

import streamlit as st

SESSION_FARMER_KEY = "current_farmer"
SESSION_ACTIVE_FIELD_KEY = "active_field"
SESSION_ACTIVE_CHAT_KEY = "active_chat_session_id"


def clear_user_session_state() -> None:
    """Clear all session state keys tied to user scans, active field, and chats."""
    keys_to_clear = [
        SESSION_ACTIVE_FIELD_KEY,
        SESSION_ACTIVE_CHAT_KEY,
        "_loaded_chat_session_id",
        "kisan_chat_messages",
        "active_scan_id",
        "analysis_outcome",
        "analysis_request",
        "kisan_thread_selector",
        "farmer_field_selector",
        "chk_show_all_scans",
        "last_handled_pill",
        "kisan_quick_pills",
        "my_location_coords",
    ]
    for k in keys_to_clear:
        st.session_state.pop(k, None)


def get_current_farmer() -> Optional[Dict[str, Any]]:
    """Return currently authenticated farmer dict or None."""
    return st.session_state.get(SESSION_FARMER_KEY)


def is_authenticated() -> bool:
    """Return True if a farmer is currently logged in."""
    return get_current_farmer() is not None


def login_farmer(farmer: Dict[str, Any]) -> None:
    """Store farmer profile in session state and synchronize preferences."""
    clear_user_session_state()
    st.session_state[SESSION_FARMER_KEY] = farmer
    pref_lang = farmer.get("preferred_language")
    if pref_lang:
        st.session_state["selected_language"] = pref_lang


def logout_farmer() -> None:
    """Clear farmer session and reset field/chat references."""
    st.session_state.pop(SESSION_FARMER_KEY, None)
    clear_user_session_state()


def get_active_field() -> Optional[Dict[str, Any]]:
    """Return currently active farm field parcel or None."""
    field = st.session_state.get(SESSION_ACTIVE_FIELD_KEY)
    if not field:
        return None
    farmer = get_current_farmer()
    if farmer and field.get("farmer_id") and field.get("farmer_id") != farmer.get("id"):
        st.session_state.pop(SESSION_ACTIVE_FIELD_KEY, None)
        return None
    return field


def set_active_field(field: Optional[Dict[str, Any]]) -> None:
    """Set active field in session state."""
    if field is None:
        st.session_state.pop(SESSION_ACTIVE_FIELD_KEY, None)
    else:
        st.session_state[SESSION_ACTIVE_FIELD_KEY] = field
