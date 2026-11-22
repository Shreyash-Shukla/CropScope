"""Tests for CropScope database layer (SQLite engine).
"""

import os
import tempfile
import unittest

from db import (
    archive_chat_session,
    archive_field,
    authenticate_farmer,
    create_chat_session,
    create_farmer,
    get_chat_history,
    get_farmer_by_id,
    get_farmer_by_identifier,
    get_field_by_id,
    get_scan_by_id,
    hash_secret,
    init_db,
    list_chat_sessions,
    list_fields,
    list_scans_for_farmer,
    list_scans_for_field,
    save_chat_message,
    save_field,
    save_scan,
    set_primary_field,
    update_farmer_profile,
    verify_secret,
)


class TestDatabaseLayer(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.db_path = self.tmp.name
        init_db(self.db_path)

    def tearDown(self):
        if os.path.exists(self.db_path):
            try:
                os.remove(self.db_path)
            except OSError:
                pass

    def test_hashing_and_verification(self):
        secret = "123456"
        hashed = hash_secret(secret)
        self.assertNotEqual(secret, hashed)
        self.assertIn(":", hashed)
        self.assertTrue(verify_secret("123456", hashed))
        self.assertFalse(verify_secret("654321", hashed))
        self.assertFalse(verify_secret("", hashed))
        self.assertFalse(verify_secret("123456", "invalid-hash"))

    def test_farmer_crud_and_auth(self):
        farmer = create_farmer(
            full_name="Ramesh Kumar",
            email="ramesh@example.com",
            phone_number="9876543210",
            password="FarmPassword@123",
            mpin="1234",
            preferred_language="hi",
            state="Punjab",
            district="Ludhiana",
            village="Samrala",
            db_path=self.db_path,
        )
        self.assertIsNotNone(farmer["id"])
        self.assertEqual(farmer["full_name"], "Ramesh Kumar")
        self.assertEqual(farmer["preferred_language"], "hi")
        self.assertNotIn("password_hash", farmer)
        self.assertNotIn("mpin_hash", farmer)

        # Duplicate email/phone prevention
        with self.assertRaises(ValueError):
            create_farmer(
                full_name="Duplicate",
                email="ramesh@example.com",
                password="password123",
                db_path=self.db_path,
            )

        # Lookup by id
        fetched = get_farmer_by_id(farmer["id"], db_path=self.db_path)
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched["email"], "ramesh@example.com")

        # Lookup by identifier (phone & email)
        by_email = get_farmer_by_identifier("ramesh@example.com", db_path=self.db_path)
        self.assertIsNotNone(by_email)
        self.assertEqual(by_email["id"], farmer["id"])

        by_phone = get_farmer_by_identifier("9876543210", db_path=self.db_path)
        self.assertIsNotNone(by_phone)
        self.assertEqual(by_phone["id"], farmer["id"])

        # Authenticate via password
        auth_pw = authenticate_farmer("ramesh@example.com", password="FarmPassword@123", db_path=self.db_path)
        self.assertIsNotNone(auth_pw)
        self.assertEqual(auth_pw["id"], farmer["id"])
        self.assertIsNotNone(auth_pw["last_login_at"])

        # Authenticate via MPIN using phone
        auth_mpin = authenticate_farmer("9876543210", mpin="1234", db_path=self.db_path)
        self.assertIsNotNone(auth_mpin)

        # Authenticate via phone with +91 country prefix
        auth_prefix = authenticate_farmer("+919876543210", mpin="1234", db_path=self.db_path)
        self.assertIsNotNone(auth_prefix)
        self.assertEqual(auth_prefix["id"], farmer["id"])

        # Failed auth
        self.assertIsNone(authenticate_farmer("ramesh@example.com", password="wrong", db_path=self.db_path))
        self.assertIsNone(authenticate_farmer("9876543210", mpin="9999", db_path=self.db_path))

        # Invalid MPIN format check
        with self.assertRaises(ValueError):
            create_farmer(full_name="Bad MPIN", phone_number="9999999999", mpin="12", db_path=self.db_path)

        # Update profile
        updated = update_farmer_profile(
            farmer["id"],
            {"preferred_language": "pa", "full_name": "Sardar Ramesh Singh"},
            db_path=self.db_path,
        )
        self.assertEqual(updated["preferred_language"], "pa")
        self.assertEqual(updated["full_name"], "Sardar Ramesh Singh")

    def test_field_management(self):
        farmer = create_farmer(
            full_name="Suresh Patel",
            phone_number="9876500000",
            mpin="4321",
            db_path=self.db_path,
        )
        bbox = (28.45, 77.01, 28.48, 77.05)
        field1 = save_field(
            farmer_id=farmer["id"],
            name="उत्तर वाला खेत (North Parcel)",
            bbox=bbox,
            soil_type="Alluvial Loam",
            irrigation_source="Canal",
            is_primary=True,
            db_path=self.db_path,
        )
        self.assertIsNotNone(field1["id"])
        self.assertTrue(field1["is_primary"])
        self.assertGreater(field1["area_ha"], 0)
        self.assertEqual(field1["boundary_geojson"]["type"], "Polygon")

        # Second field
        field2 = save_field(
            farmer_id=farmer["id"],
            name="दक्षिण वाला खेत (South Parcel)",
            bbox=(28.40, 77.01, 28.42, 77.03),
            is_primary=False,
            db_path=self.db_path,
        )

        fields = list_fields(farmer["id"], db_path=self.db_path)
        self.assertEqual(len(fields), 2)
        self.assertEqual(fields[0]["id"], field1["id"])  # Primary first

        # Switch primary field
        set_primary_field(farmer["id"], field2["id"], db_path=self.db_path)
        fields_reordered = list_fields(farmer["id"], db_path=self.db_path)
        self.assertEqual(fields_reordered[0]["id"], field2["id"])

        # Archive field
        archive_field(field1["id"], db_path=self.db_path)
        active_fields = list_fields(farmer["id"], include_archived=False, db_path=self.db_path)
        self.assertEqual(len(active_fields), 1)
        self.assertEqual(active_fields[0]["id"], field2["id"])

        all_fields = list_fields(farmer["id"], include_archived=True, db_path=self.db_path)
        self.assertEqual(len(all_fields), 2)

    def test_scans_and_telemetry(self):
        farmer = create_farmer(
            full_name="Kavita Devi",
            email="kavita@example.com",
            password="SafePassword99",
            db_path=self.db_path,
        )
        field = save_field(
            farmer_id=farmer["id"],
            name="धान का खेत (Rice field)",
            bbox=(25.31, 82.97, 25.33, 82.99),
            db_path=self.db_path,
        )

        scan = save_scan(
            farmer_id=farmer["id"],
            field_id=field["id"],
            crop_name="Rice",
            growth_stage="Tillering",
            bbox=(25.31, 82.97, 25.33, 82.99),
            weather_ok=True,
            rain_7d_mm=12.5,
            et0_7d_mm=28.0,
            net_water_mm=-15.5,
            water_status="Deficit",
            safe_to_spray_48h=True,
            satellite_ok=True,
            mean_ndvi=0.62,
            median_ndvi=0.64,
            mean_savi=0.58,
            valid_pixels_pct=98.5,
            cloud_cover_pct=1.5,
            advisory_source="Gemini-ranked",
            recommendations=[
                {
                    "action_id": "spray_check",
                    "category": "Protection",
                    "urgency": "High",
                    "title": "Clear 48h Spray Window",
                    "description": "Safe conditions for preventive spray.",
                }
            ],
            db_path=self.db_path,
        )

        self.assertIsNotNone(scan["id"])
        self.assertEqual(scan["crop_name"], "Rice")
        self.assertEqual(len(scan["recommendations"]), 1)
        self.assertEqual(scan["recommendations"][0]["action_id"], "spray_check")

        # Query scans by field and farmer
        field_scans = list_scans_for_field(field["id"], db_path=self.db_path)
        self.assertEqual(len(field_scans), 1)

        farmer_scans = list_scans_for_farmer(farmer["id"], db_path=self.db_path)
        self.assertEqual(len(farmer_scans), 1)

        fetched_scan = get_scan_by_id(scan["id"], db_path=self.db_path)
        self.assertIsNotNone(fetched_scan)
        self.assertEqual(fetched_scan["mean_ndvi"], 0.62)

    def test_kisan_mitra_chat_persistence(self):
        farmer = create_farmer(
            full_name="Mukesh Yadav",
            phone_number="9123456789",
            mpin="0000",
            db_path=self.db_path,
        )
        session = create_chat_session(
            farmer_id=farmer["id"],
            title="गेहूं में पीला रतुआ (Yellow Rust Enquiry)",
            language="hi",
            db_path=self.db_path,
        )
        self.assertIsNotNone(session["id"])
        self.assertEqual(session["language"], "hi")

        # Save user message
        save_chat_message(
            session_id=session["id"],
            role="user",
            content="मेरी गेहूं की फसल में पत्तियां पीली पड़ रही हैं। क्या करूं?",
            db_path=self.db_path,
        )

        # Save assistant message with dossier snapshot
        save_chat_message(
            session_id=session["id"],
            role="assistant",
            content="ग्राउंडेड सलाह: यह पीला रतुआ (Yellow Rust) हो सकता है। प्रॉपिकोनाज़ोल का छिड़काव करें।",
            dossier_snapshot={"crop": "Wheat", "stage": "Tillering", "ndvi": 0.45},
            db_path=self.db_path,
        )

        history = get_chat_history(session["id"], db_path=self.db_path)
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0]["role"], "user")
        self.assertEqual(history[1]["role"], "assistant")
        self.assertIn("Wheat", history[1]["dossier_snapshot"]["crop"])

        # Check session list
        sessions = list_chat_sessions(farmer["id"], db_path=self.db_path)
        self.assertEqual(len(sessions), 1)

        # Create an empty ghost session and verify only_with_messages filters it out
        empty_session = create_chat_session(
            farmer_id=farmer["id"],
            title="Empty Session",
            language="en",
            db_path=self.db_path,
        )
        all_sessions = list_chat_sessions(farmer["id"], db_path=self.db_path, only_with_messages=False)
        self.assertEqual(len(all_sessions), 2)
        non_empty_sessions = list_chat_sessions(farmer["id"], db_path=self.db_path, only_with_messages=True)
        self.assertEqual(len(non_empty_sessions), 1)
        self.assertEqual(non_empty_sessions[0]["id"], session["id"])

        # Archive session
        archive_chat_session(session["id"], db_path=self.db_path)
        active_sessions = list_chat_sessions(farmer["id"], include_archived=False, db_path=self.db_path)
        self.assertEqual(len(active_sessions), 1)  # only empty_session remains active


if __name__ == "__main__":
    unittest.main()
