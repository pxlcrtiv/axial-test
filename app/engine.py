"""State engine: applies extraction results and message intents to storage.

Transitions (each writes a line_events audit row + a messages disposition):

  create    -- new quote for a customer ("aparte", or the first request)
  update    -- a line's qty changes on an existing quote
  linked    -- a conversation joins a quote (event 2: link only, no line change)
  needs_review -- ambiguous ("mejor cancelalo"): parked, nothing changes
  ignored_duplicate -- same message_id seen before: no-op (webhook retry)

Routing rule (event 4's answer): a message is assigned by WHAT IT REFERENCES
(explicit product mention -> candidate quotes for that customer carrying the
family's SKU), never by which chat it arrived in. Exactly one candidate ->
apply. Several -> review queue. None -> create-new only if the message is a
fresh request, else review queue.
"""
import json
from datetime import datetime, timezone

from .db import get_db


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def next_quote_id(conn) -> str:
    row = conn.execute("SELECT MAX(id) AS m FROM quotes").fetchone()
    n = int(row["m"].split("-")[1]) + 1 if row and row["m"] else 1
    return f"Q-{n:03d}"


def ensure_conversation(conn, conversation_id: str, customer_id: str):
    conn.execute(
        "INSERT OR IGNORE INTO conversations (id, customer_id) VALUES (?, ?)",
        (conversation_id, customer_id),
    )


def link_conversation(conn, quote_id: str, conversation_id: str, message_id: str):
    conn.execute(
        "INSERT OR IGNORE INTO quote_conversations (quote_id, conversation_id, linked_at) "
        "VALUES (?, ?, ?)",
        (quote_id, conversation_id, _now()),
    )


def create_quote(conn, customer_id: str, conversation_id: str,
                 line_items: list[dict], message_id: str) -> str:
    quote_id = next_quote_id(conn)
    conn.execute(
        "INSERT INTO quotes (id, customer_id, status, created_at) VALUES (?, ?, 'draft', ?)",
        (quote_id, customer_id, _now()),
    )
    link_conversation(conn, quote_id, conversation_id, message_id)
    for li in line_items:
        conn.execute(
            "INSERT INTO quote_lines (quote_id, sku, qty) VALUES (?, ?, ?)",
            (quote_id, li["sku"], li["qty"]),
        )
        conn.execute(
            "INSERT INTO line_events (quote_id, sku, old_qty, new_qty, cause, message_id, timestamp) "
            "VALUES (?, ?, NULL, ?, 'created', ?, ?)",
            (quote_id, li["sku"], li["qty"], message_id, _now()),
        )
    return quote_id


def record_message(conn, message_id: str, conversation_id: str, customer_id: str,
                   direction: str, timestamp: str, text: str,
                   disposition: str, quote_id: str | None = None):
    conn.execute(
        "INSERT OR IGNORE INTO messages (message_id, conversation_id, customer_id, "
        "direction, timestamp, text, disposition, quote_id) VALUES (?,?,?,?,?,?,?,?)",
        (message_id, conversation_id, customer_id, direction, timestamp, text,
         disposition, quote_id),
    )


def is_duplicate(conn, message_id: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM messages WHERE message_id = ?", (message_id,)
    ).fetchone() is not None
