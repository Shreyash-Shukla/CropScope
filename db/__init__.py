"""CropScope Database and Data Access Layer.
"""

from db.connection import get_db_path, get_sqlite_conn, get_supabase_client, init_db, is_supabase_configured
from db.farmers import (
    authenticate_farmer,
    create_farmer,
    get_farmer_by_id,
    get_farmer_by_identifier,
    hash_secret,
    update_farmer_profile,
    verify_secret,
)
from db.fields import (
    archive_field,
    get_field_by_id,
    list_fields,
    save_field,
    set_primary_field,
)
from db.scans import (
    get_scan_by_id,
    list_scans_for_farmer,
    list_scans_for_field,
    save_scan,
)
from db.chat import (
    archive_chat_session,
    create_chat_session,
    get_chat_history,
    get_chat_session,
    list_chat_sessions,
    save_chat_message,
)

__all__ = [
    "init_db",
    "get_db_path",
    "get_sqlite_conn",
    "get_supabase_client",
    "is_supabase_configured",
    "hash_secret",
    "verify_secret",
    "create_farmer",
    "get_farmer_by_id",
    "get_farmer_by_identifier",
    "authenticate_farmer",
    "update_farmer_profile",
    "save_field",
    "get_field_by_id",
    "list_fields",
    "archive_field",
    "set_primary_field",
    "save_scan",
    "get_scan_by_id",
    "list_scans_for_field",
    "list_scans_for_farmer",
    "create_chat_session",
    "get_chat_session",
    "list_chat_sessions",
    "save_chat_message",
    "get_chat_history",
    "archive_chat_session",
]
