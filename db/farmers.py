"""Farmer account management, authentication, and profile persistence.
"""

from __future__ import annotations

import datetime
import hashlib
import hmac
import os
import re
import uuid
from typing import Any, Dict, Optional

from db.connection import (
    deserialize_json_field,
    get_sqlite_conn,
    get_supabase_client,
    is_supabase_configured,
)


def hash_secret(secret: str) -> str:
    """Hash password or MPIN using PBKDF2-HMAC-SHA256 with a 16-byte random salt."""
    if not secret:
        return ""
    salt = os.urandom(16)
    key = hashlib.pbkdf2_hmac("sha256", secret.encode("utf-8"), salt, 100_000)
    return f"{salt.hex()}:{key.hex()}"


def verify_secret(secret: str, stored_hash: Optional[str]) -> bool:
    """Verify plain secret against stored salt:key hash in constant time."""
    if not secret or not stored_hash or ":" not in stored_hash:
        return False
    try:
        salt_hex, key_hex = stored_hash.split(":", 1)
        salt = bytes.fromhex(salt_hex)
        expected_key = hashlib.pbkdf2_hmac("sha256", secret.encode("utf-8"), salt, 100_000)
        return hmac.compare_digest(expected_key.hex(), key_hex)
    except Exception:
        return False


def _clean_farmer_dict(row_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Return farmer profile dict with sensitive hashes removed and clean types."""
    res = dict(row_dict)
    res.pop("password_hash", None)
    res.pop("mpin_hash", None)
    if "is_onboarded" in res:
        res["is_onboarded"] = bool(res["is_onboarded"])
    if "is_active" in res:
        res["is_active"] = bool(res["is_active"])
    return res


def create_farmer(
    full_name: str,
    email: Optional[str] = None,
    phone_number: Optional[str] = None,
    password: Optional[str] = None,
    mpin: Optional[str] = None,
    preferred_language: str = "en",
    state: Optional[str] = None,
    district: Optional[str] = None,
    village: Optional[str] = None,
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Register a new farmer in database.
    
    Raises:
        ValueError: If neither email nor phone provided, or if already registered.
    """
    clean_email = email.strip().lower() if email and email.strip() else None
    clean_phone = re.sub(r"[^\d+]", "", phone_number.strip()) if phone_number and phone_number.strip() else None

    if not clean_email and not clean_phone:
        raise ValueError("At least one contact identifier (email or phone number) is required.")

    if not password and not mpin:
        raise ValueError("Either a password or MPIN must be set for authentication.")

    farmer_id = str(uuid.uuid4())
    pw_hash = hash_secret(password) if password else None
    mpin_h = hash_secret(mpin) if mpin else None
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

    if is_supabase_configured() and not db_path:
        sb = get_supabase_client()
        if sb:
            payload = {
                "id": farmer_id,
                "email": clean_email,
                "phone_number": clean_phone,
                "full_name": full_name.strip(),
                "password_hash": pw_hash,
                "mpin_hash": mpin_h,
                "preferred_language": preferred_language,
                "state": state,
                "district": district,
                "village": village,
                "is_onboarded": False,
                "is_active": True,
                "created_at": now_iso,
                "updated_at": now_iso,
            }
            res = sb.table("farmers").insert(payload).execute()
            if res.data:
                return _clean_farmer_dict(res.data[0])

    # Local SQLite engine
    conn = get_sqlite_conn(db_path)
    try:
        with conn:
            conn.execute(
                """
                INSERT INTO farmers (
                    id, email, phone_number, full_name, password_hash, mpin_hash,
                    preferred_language, state, district, village, is_onboarded,
                    is_active, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    farmer_id,
                    clean_email,
                    clean_phone,
                    full_name.strip(),
                    pw_hash,
                    mpin_h,
                    preferred_language,
                    state,
                    district,
                    village,
                    0,
                    1,
                    now_iso,
                    now_iso,
                ),
            )
    except Exception as e:
        err_msg = str(e).lower()
        if "unique" in err_msg or "constraint" in err_msg:
            raise ValueError("A farmer with this email or phone number already exists.") from e
        raise

    return get_farmer_by_id(farmer_id, db_path=db_path)  # type: ignore


def get_farmer_by_id(farmer_id: str, db_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Retrieve farmer profile by unique UUID."""
    if is_supabase_configured() and not db_path:
        sb = get_supabase_client()
        if sb:
            res = sb.table("farmers").select("*").eq("id", farmer_id).execute()
            if res.data:
                return _clean_farmer_dict(res.data[0])
            return None

    conn = get_sqlite_conn(db_path)
    cur = conn.cursor()
    cur.execute("SELECT * FROM farmers WHERE id = ?", (farmer_id,))
    row = cur.fetchone()
    if not row:
        return None
    return _clean_farmer_dict(dict(row))


def get_farmer_by_identifier(identifier: str, db_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Find farmer by email or phone number (including credentials for auth check)."""
    clean_id = identifier.strip()
    if not clean_id:
        return None

    is_email = "@" in clean_id
    clean_email = clean_id.lower() if is_email else None
    clean_phone = re.sub(r"[^\d+]", "", clean_id) if not is_email else None

    if is_supabase_configured() and not db_path:
        sb = get_supabase_client()
        if sb:
            query = sb.table("farmers").select("*")
            if is_email:
                res = query.eq("email", clean_email).execute()
            else:
                res = query.eq("phone_number", clean_phone).execute()
            if res.data:
                return dict(res.data[0])
            return None

    conn = get_sqlite_conn(db_path)
    cur = conn.cursor()
    if is_email:
        cur.execute("SELECT * FROM farmers WHERE email = ?", (clean_email,))
    else:
        cur.execute("SELECT * FROM farmers WHERE phone_number = ?", (clean_phone,))
    row = cur.fetchone()
    if not row:
        return None
    return dict(row)


def authenticate_farmer(
    identifier: str,
    password: Optional[str] = None,
    mpin: Optional[str] = None,
    db_path: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Authenticate farmer with password or MPIN. Returns profile dict on success."""
    farmer = get_farmer_by_identifier(identifier, db_path=db_path)
    if not farmer:
        return None

    is_active = farmer.get("is_active", 1)
    if not is_active:
        return None

    verified = False
    if password and farmer.get("password_hash"):
        verified = verify_secret(password, farmer["password_hash"])
    elif mpin and farmer.get("mpin_hash"):
        verified = verify_secret(mpin, farmer["mpin_hash"])

    if not verified:
        return None

    # Update last login timestamp
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    farmer_id = farmer["id"]
    if is_supabase_configured() and not db_path:
        sb = get_supabase_client()
        if sb:
            sb.table("farmers").update({"last_login_at": now_iso}).eq("id", farmer_id).execute()
    else:
        conn = get_sqlite_conn(db_path)
        with conn:
            conn.execute("UPDATE farmers SET last_login_at = ? WHERE id = ?", (now_iso, farmer_id))

    farmer["last_login_at"] = now_iso
    return _clean_farmer_dict(farmer)


def update_farmer_profile(
    farmer_id: str,
    updates: Dict[str, Any],
    db_path: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Update profile attributes (e.g. language, location, full_name)."""
    allowed_fields = {
        "full_name",
        "preferred_language",
        "state",
        "district",
        "village",
        "is_onboarded",
    }
    filtered = {k: v for k, v in updates.items() if k in allowed_fields}
    if not filtered:
        return get_farmer_by_id(farmer_id, db_path=db_path)

    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    filtered["updated_at"] = now_iso

    if is_supabase_configured() and not db_path:
        sb = get_supabase_client()
        if sb:
            res = sb.table("farmers").update(filtered).eq("id", farmer_id).execute()
            if res.data:
                return _clean_farmer_dict(res.data[0])
            return None

    conn = get_sqlite_conn(db_path)
    set_clause = ", ".join(f"{k} = ?" for k in filtered.keys())
    values = list(filtered.values())
    values.append(farmer_id)
    with conn:
        conn.execute(f"UPDATE farmers SET {set_clause} WHERE id = ?", values)

    return get_farmer_by_id(farmer_id, db_path=db_path)
