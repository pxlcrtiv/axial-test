"""SQLite storage. Survives process restart by construction (file on disk).

Schema (the data model from the README):

  customers(id, name)
  conversations(id, customer_id)          -- a WhatsApp chat
  quotes(id, customer_id, status)         -- an Oferta de Venta
  quote_conversations(quote_id, conversation_id)   <-- MANY-TO-MANY junction
  quote_lines(quote_id, sku, qty)         -- no conversation reference, ever
  messages(message_id PK, ...)            -- dedupe by primary key
  line_events(...)                        -- audit: what changed, which message
  pending_assignments(...)                -- the "mejor cancelalo" queue

Neither quotes nor conversations carry each other's id: the junction absorbs
event 2 (second chat -> existing quote) and event 3 (second quote, same chat).
"""
import os
import sqlite3
from contextlib import contextmanager

SCHEMA = """
CREATE TABLE IF NOT EXISTS customers (
    id   TEXT PRIMARY KEY,
    name TEXT
);
CREATE TABLE IF NOT EXISTS conversations (
    id          TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS quotes (
    id          TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'draft',
    created_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS quote_conversations (
    quote_id        TEXT NOT NULL,
    conversation_id TEXT NOT NULL,
    linked_at       TEXT NOT NULL,
    PRIMARY KEY (quote_id, conversation_id)
);
CREATE TABLE IF NOT EXISTS quote_lines (
    quote_id TEXT NOT NULL,
    sku      TEXT NOT NULL,
    qty      INTEGER NOT NULL,
    PRIMARY KEY (quote_id, sku)
);
CREATE TABLE IF NOT EXISTS messages (
    message_id      TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL,
    customer_id     TEXT NOT NULL,
    direction       TEXT NOT NULL,
    timestamp       TEXT NOT NULL,
    text            TEXT NOT NULL,
    disposition     TEXT NOT NULL,
    quote_id        TEXT
);
CREATE TABLE IF NOT EXISTS line_events (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    quote_id   TEXT NOT NULL,
    sku        TEXT,                     -- NULL for link-only events
    old_qty    INTEGER,
    new_qty    INTEGER,
    cause      TEXT NOT NULL,          -- created | updated | linked
    message_id TEXT NOT NULL,
    timestamp  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS pending_assignments (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id          TEXT NOT NULL,
    conversation_id     TEXT NOT NULL,
    customer_id         TEXT NOT NULL,
    text                TEXT NOT NULL,
    candidate_quote_ids TEXT NOT NULL,  -- JSON list
    reason              TEXT NOT NULL,
    status              TEXT NOT NULL DEFAULT 'pending',  -- pending | resolved
    resolution          TEXT,           -- applied | discarded
    resolved_by         TEXT,           -- who/what decided (required at API)
    resolved_quote_id   TEXT
);
"""


def db_path() -> str:
    return os.environ.get("QUOTES_DB_PATH", "quotes.db")


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)


@contextmanager
def get_db():
    conn = connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()
