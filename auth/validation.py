"""Validation rules and regex sanitizers for farmer authentication and registration.
"""

from __future__ import annotations

import re
from typing import Optional, Tuple

# Indian mobile numbers: 10 digits starting with 6, 7, 8, or 9
PHONE_REGEX = re.compile(r"^[6-9]\d{9}$")
# Standard email format
EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")
# 4-Digit MPIN
MPIN_REGEX = re.compile(r"^\d{4}$")


def validate_full_name(name: str) -> Tuple[bool, Optional[str]]:
    """Validate full name: non-empty, minimum 2 characters."""
    stripped = name.strip() if name else ""
    if not stripped:
        return False, "Please enter your full name / कृपया अपना नाम दर्ज करें।"
    if len(stripped) < 2:
        return False, "Full name must be at least 2 characters long / नाम कम से कम 2 अक्षरों का होना चाहिए।"
    return True, None


def normalize_and_validate_phone(phone: Optional[str]) -> Tuple[bool, Optional[str], Optional[str]]:
    """Normalize phone number and validate against 10-digit mobile format.
    
    Returns:
        (is_valid, normalized_phone, error_message)
    """
    if not phone or not phone.strip():
        return True, None, None  # Optional field
    
    raw = phone.strip()
    digits = re.sub(r"[^\d]", "", raw)
    # Strip leading country code 91 if 12 digits
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    # Strip leading 0 if 11 digits
    elif len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]

    if not PHONE_REGEX.match(digits):
        return False, None, "Please enter a valid 10-digit mobile number (e.g. 9876543210) / कृपया सही 10-अंकों का मोबाइल नंबर दर्ज करें।"

    return True, digits, None


def validate_email(email: Optional[str]) -> Tuple[bool, Optional[str], Optional[str]]:
    """Validate email format.
    
    Returns:
        (is_valid, clean_email, error_message)
    """
    if not email or not email.strip():
        return True, None, None  # Optional field

    clean = email.strip().lower()
    if not EMAIL_REGEX.match(clean):
        return False, None, "Please enter a valid email address (e.g. name@farm.com) / कृपया सही ईमेल दर्ज करें।"
    return True, clean, None


def validate_mpin(mpin: Optional[str]) -> Tuple[bool, Optional[str]]:
    """Validate 4-digit numeric MPIN."""
    if not mpin or not mpin.strip():
        return True, None  # Optional if password provided
    clean = mpin.strip()
    if not MPIN_REGEX.match(clean):
        return False, "MPIN must be exactly 4 numeric digits (e.g. 1234) / एमपिन ठीक 4 अंकों का होना चाहिए।"
    return True, None


def validate_password(password: Optional[str]) -> Tuple[bool, Optional[str]]:
    """Validate password: minimum 6 characters if provided."""
    if not password:
        return True, None  # Optional if MPIN provided
    if len(password) < 6:
        return False, "Password must be at least 6 characters long / पासवर्ड कम से कम 6 अक्षरों का होना चाहिए।"
    return True, None


def validate_login_identifier(identifier: str) -> Tuple[bool, Optional[str], Optional[str]]:
    """Validate login identifier (either valid email or 10-digit phone number).
    
    Returns:
        (is_valid, normalized_identifier, error_message)
    """
    clean = identifier.strip()
    if not clean:
        return False, None, "Please enter your mobile number or email / कृपया मोबाइल नंबर या ईमेल दर्ज करें।"

    if "@" in clean:
        val_ok, norm_email, err = validate_email(clean)
        return val_ok, norm_email, err
    else:
        val_ok, norm_phone, err = normalize_and_validate_phone(clean)
        return val_ok, norm_phone, err
