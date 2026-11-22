"""Tests for authentication and registration input validation and regex sanitizers.
"""

import unittest

from auth.validation import (
    normalize_and_validate_phone,
    validate_email,
    validate_full_name,
    validate_login_identifier,
    validate_mpin,
    validate_password,
)


class TestValidationRules(unittest.TestCase):
    def test_full_name_validation(self):
        # Valid names
        self.assertTrue(validate_full_name("Ramesh Kumar")[0])
        self.assertTrue(validate_full_name("Om")[0])
        self.assertTrue(validate_full_name("Balwinder Singh Dhillon")[0])

        # Invalid names
        self.assertFalse(validate_full_name("")[0])
        self.assertFalse(validate_full_name("   ")[0])
        self.assertFalse(validate_full_name("A")[0])

    def test_phone_number_regex_and_normalization(self):
        # Valid standard 10-digit mobile numbers starting with 6, 7, 8, or 9
        ok, norm, _ = normalize_and_validate_phone("9876543210")
        self.assertTrue(ok)
        self.assertEqual(norm, "9876543210")

        # +91 prefix
        ok, norm, _ = normalize_and_validate_phone("+91 9876543210")
        self.assertTrue(ok)
        self.assertEqual(norm, "9876543210")

        # 0 prefix
        ok, norm, _ = normalize_and_validate_phone("09876543210")
        self.assertTrue(ok)
        self.assertEqual(norm, "9876543210")

        # Formatted with hyphens and spaces
        ok, norm, _ = normalize_and_validate_phone("98765-43210")
        self.assertTrue(ok)
        self.assertEqual(norm, "9876543210")

        # Different starting digits (6, 7, 8, 9)
        self.assertTrue(normalize_and_validate_phone("6123456789")[0])
        self.assertTrue(normalize_and_validate_phone("7123456789")[0])
        self.assertTrue(normalize_and_validate_phone("8123456789")[0])
        self.assertTrue(normalize_and_validate_phone("9123456789")[0])

        # Invalid phone numbers
        self.assertFalse(normalize_and_validate_phone("1234567890")[0])  # starts with 1
        self.assertFalse(normalize_and_validate_phone("12345")[0])       # too short
        self.assertFalse(normalize_and_validate_phone("987654321012")[0]) # too long
        self.assertFalse(normalize_and_validate_phone("abcdefghij")[0]) # non-digits

        # Optional empty phone returns True, None
        ok_empty, norm_empty, err_empty = normalize_and_validate_phone("")
        self.assertTrue(ok_empty)
        self.assertIsNone(norm_empty)
        self.assertIsNone(err_empty)

    def test_email_regex_validation(self):
        # Valid emails
        self.assertTrue(validate_email("farmer@cropscope.io")[0])
        self.assertTrue(validate_email("ramesh.kumar+field1@farm.co.in")[0])

        # Invalid emails
        self.assertFalse(validate_email("invalid-email")[0])
        self.assertFalse(validate_email("user@")[0])
        self.assertFalse(validate_email("@domain.com")[0])
        self.assertFalse(validate_email("user@domain")[0])

        # Optional empty email
        ok_empty, clean_empty, _ = validate_email("")
        self.assertTrue(ok_empty)
        self.assertIsNone(clean_empty)

    def test_mpin_regex_validation(self):
        # Exactly 4 numeric digits
        self.assertTrue(validate_mpin("1234")[0])
        self.assertTrue(validate_mpin("0000")[0])
        self.assertTrue(validate_mpin("9999")[0])

        # Invalid MPINs
        self.assertFalse(validate_mpin("12")[0])
        self.assertFalse(validate_mpin("123")[0])
        self.assertFalse(validate_mpin("12345")[0])
        self.assertFalse(validate_mpin("12a4")[0])
        self.assertFalse(validate_mpin("abcd")[0])

    def test_password_length_validation(self):
        self.assertTrue(validate_password("pass12")[0])  # 6 chars
        self.assertTrue(validate_password("StrongPassword@2026")[0])

        # Less than 6 characters
        self.assertFalse(validate_password("12345")[0])
        self.assertFalse(validate_password("abc")[0])

    def test_login_identifier_validation(self):
        # Mobile number login
        ok, norm, _ = validate_login_identifier("9876543210")
        self.assertTrue(ok)
        self.assertEqual(norm, "9876543210")

        # Mobile with +91
        ok, norm, _ = validate_login_identifier("+91 9876543210")
        self.assertTrue(ok)
        self.assertEqual(norm, "9876543210")

        # Email login
        ok, norm, _ = validate_login_identifier("ramesh@farm.com")
        self.assertTrue(ok)
        self.assertEqual(norm, "ramesh@farm.com")

        # Blank or invalid
        self.assertFalse(validate_login_identifier("")[0])
        self.assertFalse(validate_login_identifier("bad-input")[0])


if __name__ == "__main__":
    unittest.main()
