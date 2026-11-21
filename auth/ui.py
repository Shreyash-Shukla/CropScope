"""Farmer authentication UI components styled with CropScope Watched.earth design system.
"""

from __future__ import annotations

from typing import Optional

import streamlit as st

from auth.session import (
    get_active_field,
    get_current_farmer,
    is_authenticated,
    login_farmer,
    logout_farmer,
)
from db.farmers import authenticate_farmer, create_farmer
from db.scans import list_scans_for_farmer, list_scans_for_field
from i18n import SUPPORTED_LANGUAGES, t


def render_auth_header_widget(current_lang: str) -> bool:
    """Render top-bar authentication indicator and toggle switch.
    
    Returns True if the account drawer should be opened.
    """
    farmer = get_current_farmer()

    if farmer:
        name = farmer.get("full_name") or "Farmer"
        loc_parts = [p for p in [farmer.get("village"), farmer.get("district"), farmer.get("state")] if p]
        loc_str = f" ({', '.join(loc_parts[:2])})" if loc_parts else ""
        
        st.markdown(
            f"""
            <div style="font-family: var(--font-mono); font-size: 11px; color: var(--bone);
                        background: var(--ink-1); border: 1px solid var(--line);
                        padding: 5px 8px; display: flex; align-items: center; gap: 6px;
                        text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 4px;
                        white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">
                <span style="color: var(--signal);">👤</span>
                <span style="font-weight: 700; overflow: hidden; text-overflow: ellipsis;">{name}{loc_str}</span>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return st.toggle("👤 Account / खाता", key="toggle_farmer_account", help="View your farm profile and account settings")
    else:
        st.markdown(
            """
            <div style="font-family: var(--font-mono); font-size: 11px; color: var(--bone-3);
                        background: var(--ink-1); border: 1px solid var(--line);
                        padding: 5px 8px; display: flex; align-items: center; gap: 6px;
                        text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 4px;
                        white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">
                <span style="opacity: 0.6;">👤</span>
                <span>Guest / अतिथि</span>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return st.toggle("🔑 Login / खाता", key="toggle_farmer_account", help="Login to save farm fields, scans, and chat threads")


def render_auth_drawer(current_lang: str, is_open: bool) -> None:
    """Render expandable login/registration/profile drawer when toggle is ON."""
    if not is_open:
        return

    farmer = get_current_farmer()

    with st.container():
        if farmer:
            # Logged-in farmer profile view
            act_field = get_active_field()
            field_info = f" · Active Field: {act_field.get('name')}" if act_field else ""
            st.markdown(
                f"""
                <div style="background: var(--ink-1); border: 1px solid var(--signal);
                            border-left: 4px solid var(--signal); padding: 14px 18px; margin-bottom: 14px;">
                    <div style="font-family: var(--font-mono); font-size: 13px; font-weight: 700;
                                color: var(--bone); letter-spacing: 0.1em; text-transform: uppercase;">
                        🌾 Farmer Profile // किसान प्रोफाइल {field_info}
                    </div>
                    <div style="font-size: 12px; color: var(--bone-2); margin-top: 6px; display: flex; gap: 16px; flex-wrap: wrap;">
                        <span><strong>Name:</strong> {farmer.get('full_name')}</span>
                        <span><strong>Phone:</strong> {farmer.get('phone_number') or 'Not set'}</span>
                        <span><strong>Email:</strong> {farmer.get('email') or 'Not set'}</span>
                        <span><strong>Region:</strong> {farmer.get('district') or '-'}, {farmer.get('state') or '-'}</span>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            col_logout, col_spacer = st.columns([1, 3])
            with col_logout:
                if st.button("🚪 Logout / लॉग आउट", key="btn_logout_action", use_container_width=True):
                    logout_farmer()
                    st.session_state["toggle_farmer_account"] = False
                    try:
                        st.rerun()
                    except Exception:
                        pass
            
            # Show past scans timeline for logged in farmer
            from auth.history import render_scan_history_timeline
            render_scan_history_timeline(farmer["id"], field_id=act_field.get("id") if act_field else None, current_lang=current_lang)
            return

        # Guest view: Sign In or Register tabs
        st.markdown(
            """
            <div style="background: var(--ink-1); border: 1px solid var(--signal);
                        border-left: 4px solid var(--signal); padding: 14px 18px; margin-bottom: 14px;">
                <div style="font-family: var(--font-mono); font-size: 13px; font-weight: 700;
                            color: var(--bone); letter-spacing: 0.1em; text-transform: uppercase;">
                    🌾 Farmer Account Access // किसान खाता लॉगिन
                </div>
                <div style="font-size: 11.5px; color: var(--bone-2); margin-top: 4px;">
                    Sign in to save your farm boundaries, past satellite & weather scans, and chat history.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        tab_login, tab_register = st.tabs([
            "🔑 Sign In (लॉग इन)",
            "📝 Register (नया खाता)",
        ])

        with tab_login:
            col_id, col_cred = st.columns(2)
            with col_id:
                login_id = st.text_input(
                    "Mobile No. or Email / मोबाइल या ईमेल",
                    placeholder="e.g. 9876543210 or name@farm.com",
                    key="input_login_id",
                )
            with col_cred:
                auth_method = st.radio(
                    "Method",
                    ["Password", "4-Digit MPIN"],
                    horizontal=True,
                    key="radio_auth_method",
                )
                if auth_method == "4-Digit MPIN":
                    login_secret = st.text_input(
                        "MPIN",
                        type="password",
                        max_chars=4,
                        placeholder="••••",
                        key="input_login_mpin",
                    )
                else:
                    login_secret = st.text_input(
                        "Password / पासवर्ड",
                        type="password",
                        key="input_login_pw",
                    )

            if st.button("Sign In / प्रवेश करें", key="btn_submit_login", type="primary", use_container_width=True):
                if not login_id or not login_secret:
                    st.error("Please enter both identifier and password/MPIN.")
                else:
                    try:
                        is_mpin = auth_method == "4-Digit MPIN"
                        f_record = authenticate_farmer(
                            login_id,
                            password=None if is_mpin else login_secret,
                            mpin=login_secret if is_mpin else None,
                        )
                        if f_record:
                            login_farmer(f_record)
                            st.session_state["toggle_farmer_account"] = False
                            st.success(f"Welcome back, {f_record.get('full_name', 'Farmer')}!")
                            try:
                                st.rerun()
                            except Exception:
                                pass
                        else:
                            st.error("Invalid credentials. Please verify your mobile/email and secret.")
                    except Exception as le:
                        st.error(f"Sign-in error: {le}")

        with tab_register:
            r_name = st.text_input("Full Name / पूरा नाम *", placeholder="e.g. Ramesh Kumar", key="reg_name")
            r_col1, r_col2 = st.columns(2)
            with r_col1:
                r_phone = st.text_input("Mobile No. / मोबाइल नंबर", placeholder="e.g. 9876543210", key="reg_phone")
            with r_col2:
                r_email = st.text_input("Email (Optional) / ईमेल", placeholder="e.g. ramesh@farm.com", key="reg_email")

            r_sec1, r_sec2 = st.columns(2)
            with r_sec1:
                r_pw = st.text_input("Password (Optional)", type="password", key="reg_pw")
            with r_sec2:
                r_mpin = st.text_input("4-Digit MPIN / एमपिन", type="password", max_chars=4, placeholder="••••", key="reg_mpin")

            r_loc1, r_loc2, r_loc3 = st.columns(3)
            lang_codes = list(SUPPORTED_LANGUAGES.keys())
            lang_labels = [SUPPORTED_LANGUAGES[c]["label"] for c in lang_codes]
            with r_loc1:
                pref_lang_idx = lang_codes.index(current_lang) if current_lang in lang_codes else 0
                chosen_lang_label = st.selectbox("Preferred Language", lang_labels, index=pref_lang_idx, key="reg_lang")
                chosen_lang = lang_codes[lang_labels.index(chosen_lang_label)]
            with r_loc2:
                r_state = st.text_input("State / राज्य", placeholder="e.g. Punjab, Haryana", key="reg_state")
            with r_loc3:
                r_dist = st.text_input("District / ज़िला", placeholder="e.g. Ludhiana, Karnal", key="reg_dist")

            if st.button("Create Account & Sign In / खाता बनाएं", key="btn_submit_reg", type="primary", use_container_width=True):
                if not r_name.strip():
                    st.error("Please enter your name.")
                elif not r_phone.strip() and not r_email.strip():
                    st.error("Please provide at least a mobile number or email.")
                elif not r_pw and not r_mpin:
                    st.error("Please set either a password or a 4-digit MPIN for sign-in.")
                else:
                    try:
                        new_farmer = create_farmer(
                            full_name=r_name,
                            phone_number=r_phone or None,
                            email=r_email or None,
                            password=r_pw or None,
                            mpin=r_mpin or None,
                            preferred_language=chosen_lang,
                            state=r_state or None,
                            district=r_dist or None,
                        )
                        login_farmer(new_farmer)
                        st.session_state["toggle_farmer_account"] = False
                        st.success(f"Account created! Welcome to CropScope, {r_name}!")
                        try:
                            st.rerun()
                        except Exception:
                            pass
                    except ValueError as ve:
                        st.error(str(ve))
                    except Exception as exc:
                        st.error(f"Account creation error: {exc}")
