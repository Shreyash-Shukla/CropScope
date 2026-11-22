"""Kisan Mitra chat session and message thread persistence.
"""

from __future__ import annotations

import datetime
import uuid
from typing import Any, Dict, List, Optional

from db.connection import (
    deserialize_json_field,
    get_sqlite_conn,
    get_supabase_client,
    is_supabase_configured,
    serialize_json_field,
)


def _clean_message_row(row_dict: Dict[str, Any]) -> Dict[str, Any]:
    res = dict(row_dict)
    res["dossier_snapshot"] = deserialize_json_field(res.get("dossier_snapshot"))
    return res


def create_chat_session(
    farmer_id: str,
    title: str,
    field_id: Optional[str] = None,
    scan_id: Optional[str] = None,
    language: str = "en",
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Create a new Kisan Mitra conversation thread."""
    session_id = str(uuid.uuid4())
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

    if is_supabase_configured() and not db_path:
        sb = get_supabase_client()
        if sb:
            payload = {
                "id": session_id,
                "farmer_id": farmer_id,
                "field_id": field_id,
                "scan_id": scan_id,
                "title": title.strip() or "Chat",
                "language": language,
                "is_archived": False,
                "created_at": now_iso,
                "updated_at": now_iso,
            }
            res = sb.table("chat_sessions").insert(payload).execute()
            if res.data:
                return dict(res.data[0])

    # SQLite
    conn = get_sqlite_conn(db_path)
    with conn:
        conn.execute(
            """
            INSERT INTO chat_sessions (
                id, farmer_id, field_id, scan_id, title, language, is_archived, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?)
            """,
            (session_id, farmer_id, field_id, scan_id, title.strip() or "Chat", language, now_iso, now_iso),
        )

    res_session = get_chat_session(session_id, db_path=db_path)
    assert res_session is not None
    return res_session


def get_chat_session(session_id: str, db_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Retrieve chat session metadata."""
    if is_supabase_configured() and not db_path:
        sb = get_supabase_client()
        if sb:
            res = sb.table("chat_sessions").select("*").eq("id", session_id).execute()
            return dict(res.data[0]) if res.data else None

    conn = get_sqlite_conn(db_path)
    cur = conn.cursor()
    cur.execute("SELECT * FROM chat_sessions WHERE id = ?", (session_id,))
    row = cur.fetchone()
    return dict(row) if row else None


def list_chat_sessions(
    farmer_id: str,
    limit: int = 20,
    include_archived: bool = False,
    only_with_messages: bool = False,
    db_path: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """List recent chat conversations for a farmer."""
    if is_supabase_configured() and not db_path:
        sb = get_supabase_client()
        if sb:
            query = sb.table("chat_sessions").select("*").eq("farmer_id", farmer_id)
            if not include_archived:
                query = query.eq("is_archived", False)
            res = query.order("updated_at", desc=True).limit(limit).execute()
            return [dict(r) for r in res.data]

    conn = get_sqlite_conn(db_path)
    cur = conn.cursor()
    if only_with_messages:
        arch_filter = "" if include_archived else "AND cs.is_archived = 0"
        cur.execute(
            f"""
            SELECT cs.*, COUNT(cm.id) AS message_count
            FROM chat_sessions cs
            INNER JOIN chat_messages cm ON cs.id = cm.session_id
            WHERE cs.farmer_id = ? {arch_filter}
            GROUP BY cs.id
            ORDER BY cs.updated_at DESC LIMIT ?
            """,
            (farmer_id, limit),
        )
    elif include_archived:
        cur.execute(
            """
            SELECT * FROM chat_sessions
            WHERE farmer_id = ?
            ORDER BY updated_at DESC LIMIT ?
            """,
            (farmer_id, limit),
        )
    else:
        cur.execute(
            """
            SELECT * FROM chat_sessions
            WHERE farmer_id = ? AND is_archived = 0
            ORDER BY updated_at DESC LIMIT ?
            """,
            (farmer_id, limit),
        )
    return [dict(r) for r in cur.fetchall()]


def save_chat_message(
    session_id: str,
    role: str,
    content: str,
    dossier_snapshot: Optional[Dict[str, Any]] = None,
    tokens_used: int = 0,
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Persist a message to a session thread and update session timestamp."""
    msg_id = str(uuid.uuid4())
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

    if is_supabase_configured() and not db_path:
        sb = get_supabase_client()
        if sb:
            msg_payload = {
                "id": msg_id,
                "session_id": session_id,
                "role": role,
                "content": content,
                "dossier_snapshot": dossier_snapshot,
                "tokens_used": tokens_used,
                "created_at": now_iso,
            }
            res = sb.table("chat_messages").insert(msg_payload).execute()
            sb.table("chat_sessions").update({"updated_at": now_iso}).eq("id", session_id).execute()
            return _clean_message_row(res.data[0]) if res.data else msg_payload

    conn = get_sqlite_conn(db_path)
    with conn:
        conn.execute(
            """
            INSERT INTO chat_messages (id, session_id, role, content, dossier_snapshot, tokens_used, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (msg_id, session_id, role, content, serialize_json_field(dossier_snapshot), tokens_used, now_iso),
        )
        conn.execute("UPDATE chat_sessions SET updated_at = ? WHERE id = ?", (now_iso, session_id))

    return {
        "id": msg_id,
        "session_id": session_id,
        "role": role,
        "content": content,
        "dossier_snapshot": dossier_snapshot,
        "tokens_used": tokens_used,
        "created_at": now_iso,
    }


def get_chat_history(session_id: str, db_path: Optional[str] = None) -> List[Dict[str, Any]]:
    """Retrieve full conversation messages ordered chronologically."""
    if is_supabase_configured() and not db_path:
        sb = get_supabase_client()
        if sb:
            res = (
                sb.table("chat_messages")
                .select("*")
                .eq("session_id", session_id)
                .order("created_at", desc=False)
                .execute()
            )
            return [_clean_message_row(r) for r in res.data]

    conn = get_sqlite_conn(db_path)
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM chat_messages WHERE session_id = ? ORDER BY created_at ASC",
        (session_id,),
    )
    return [_clean_message_row(dict(r)) for r in cur.fetchall()]


def archive_chat_session(session_id: str, db_path: Optional[str] = None) -> bool:
    """Soft delete / archive a chat thread."""
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    if is_supabase_configured() and not db_path:
        sb = get_supabase_client()
        if sb:
            sb.table("chat_sessions").update({"is_archived": True, "updated_at": now_iso}).eq("id", session_id).execute()
            return True

    conn = get_sqlite_conn(db_path)
    with conn:
        conn.execute("UPDATE chat_sessions SET is_archived = 1, updated_at = ? WHERE id = ?", (now_iso, session_id))
    return True
