"""CropScope Farmer Authentication and Session Module.
"""

from auth.fields_ui import (
    render_farmer_fields_selector,
    render_save_field_widget,
)
from auth.history import (
    record_scan_outcome,
    render_scan_history_timeline,
)
from auth.session import (
    SESSION_ACTIVE_CHAT_KEY,
    SESSION_ACTIVE_FIELD_KEY,
    SESSION_FARMER_KEY,
    clear_user_session_state,
    get_active_field,
    get_current_farmer,
    is_authenticated,
    login_farmer,
    logout_farmer,
    set_active_field,
)
from auth.ui import render_auth_drawer, render_auth_header_widget

__all__ = [
    "SESSION_FARMER_KEY",
    "SESSION_ACTIVE_FIELD_KEY",
    "SESSION_ACTIVE_CHAT_KEY",
    "get_current_farmer",
    "is_authenticated",
    "login_farmer",
    "logout_farmer",
    "clear_user_session_state",
    "get_active_field",
    "set_active_field",
    "render_auth_header_widget",
    "render_auth_drawer",
    "render_farmer_fields_selector",
    "render_save_field_widget",
    "record_scan_outcome",
    "render_scan_history_timeline",
]
