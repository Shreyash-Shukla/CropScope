"""Tests for CropScope authentication and session management.
"""

import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import streamlit as st

from analysis import AnalysisOutcome, SourceState
from auth import (
    SESSION_ACTIVE_CHAT_KEY,
    SESSION_ACTIVE_FIELD_KEY,
    SESSION_FARMER_KEY,
    get_active_field,
    get_current_farmer,
    is_authenticated,
    login_farmer,
    logout_farmer,
    record_scan_outcome,
    render_auth_drawer,
    render_auth_header_widget,
    render_farmer_fields_selector,
    render_save_field_widget,
    render_scan_history_timeline,
    set_active_field,
)
from db.connection import init_db
from db.farmers import create_farmer
from db.fields import save_field
from models import AnalysisArea, AnalysisRequest


class TestAuthSession(unittest.TestCase):
    def setUp(self):
        # Clear Streamlit session state keys before each test
        for key in [
            SESSION_FARMER_KEY,
            SESSION_ACTIVE_FIELD_KEY,
            SESSION_ACTIVE_CHAT_KEY,
            "selected_language",
            "language_selector",
            "toggle_farmer_account",
            "show_auth_panel",
            "farmer_field_selector",
        ]:
            st.session_state.pop(key, None)

    def test_unauthenticated_state(self):
        self.assertFalse(is_authenticated())
        self.assertIsNone(get_current_farmer())
        self.assertIsNone(get_active_field())

    def test_login_and_logout_flow(self):
        farmer_data = {
            "id": "mock-uuid-1234",
            "full_name": "Balwinder Singh",
            "phone_number": "9812345678",
            "preferred_language": "pa",
        }
        login_farmer(farmer_data)
        self.assertTrue(is_authenticated())
        self.assertEqual(get_current_farmer()["full_name"], "Balwinder Singh")
        self.assertEqual(st.session_state.get("selected_language"), "pa")

        # Set active field
        field_data = {"id": "field-1", "name": "Khet 1"}
        set_active_field(field_data)
        self.assertEqual(get_active_field()["id"], "field-1")

        # Logout
        logout_farmer()
        self.assertFalse(is_authenticated())
        self.assertIsNone(get_current_farmer())
        self.assertIsNone(get_active_field())

    def test_set_active_field_none(self):
        set_active_field({"id": "field-2"})
        self.assertIsNotNone(get_active_field())
        set_active_field(None)
        self.assertIsNone(get_active_field())

    def test_drawer_closed_by_default(self):
        render_auth_drawer("en", is_open=False)

    def test_farmer_fields_selector_empty_when_no_fields(self):
        result = render_farmer_fields_selector("non-existent-farmer-id", "en")
        self.assertIsNone(result)

    def test_farmer_fields_selector_with_saved_field(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        try:
            init_db(tmp.name)
            farmer = create_farmer("Harpreet Singh", phone_number="9988776655", mpin="1234", db_path=tmp.name)
            saved_f = save_field(
                farmer_id=farmer["id"],
                name="Main Field",
                bbox=(29.1, 76.8, 29.2, 76.9),
                db_path=tmp.name,
            )
            with patch("auth.fields_ui.list_fields", return_value=[saved_f]):
                res_none = render_farmer_fields_selector(farmer["id"], "en")
                self.assertIsNone(res_none)
        finally:
            if os.path.exists(tmp.name):
                try:
                    os.remove(tmp.name)
                except OSError:
                    pass

    def test_record_scan_outcome_persistence(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        try:
            init_db(tmp.name)
            farmer = create_farmer("Jasbir Kaur", phone_number="9876511111", mpin="1111", db_path=tmp.name)
            req = AnalysisRequest(
                area=AnalysisArea(28.4, 77.1, 28.5, 77.2),
                crop="Wheat",
                growth_stage="Flowering",
            )
            outcome = AnalysisOutcome(
                request=req,
                weather=SourceState(None, False, None),
                satellite=SourceState(None, False, None),
                suggestions=(),
                suggestion_source="Rule-based fallback",
            )
            saved_scan = record_scan_outcome(outcome, farmer_id=farmer["id"], db_path=tmp.name)
            self.assertIsNotNone(saved_scan)
            self.assertEqual(saved_scan["crop_name"], "Wheat")
            self.assertEqual(saved_scan["growth_stage"], "Flowering")
        finally:
            if os.path.exists(tmp.name):
                try:
                    os.remove(tmp.name)
                except OSError:
                    pass

    def test_render_scan_history_timeline_empty(self):
        # Should render empty note without error
        render_scan_history_timeline("non-existent-farmer", current_lang="en")


if __name__ == "__main__":
    unittest.main()
