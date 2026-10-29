"""Quote & State Engine — headless pipeline: WhatsApp conversation -> Oferta de Venta."""
import json
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException

from .db import get_db, init_db
from .engine import (_now, create_quote, ensure_conversation, process_message,
                     record_message)
from .extract import extract_conversation
from .models import ConversationIn, MessageIn, QuotesOut, ReviewResolveIn


def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        init_db()
        yield

    app = FastAPI(title="Quote & State Engine", lifespan=lifespan)

    @app.get("/quotes")
    def list_quotes(customer: str) -> QuotesOut:
        with get_db() as conn:
            rows = conn.execute(
                "SELECT id, status FROM quotes WHERE customer_id = ? ORDER BY id",
                (customer,),
            ).fetchall()
            return {
                "quotes": [
                    {
                        "quote_id": r["id"],
                        "status": r["status"],
                        "conversations": _conversations(conn, r["id"]),
                        "line_items": _lines(conn, r["id"]),
                    }
                    for r in rows
                ]
            }

    @app.get("/quotes/{quote_id}")
    def get_quote(quote_id: str):
        """One quote with its audit history and per-message dispositions."""
        with get_db() as conn:
            row = conn.execute(
                "SELECT id, status, customer_id FROM quotes WHERE id = ?", (quote_id,)
            ).fetchone()
            if row is None:
                raise HTTPException(404, "No such quote")
            history = conn.execute(
                "SELECT sku, old_qty, new_qty, cause, message_id FROM line_events "
                "WHERE quote_id = ? ORDER BY id",
                (quote_id,),
            ).fetchall()
            messages = conn.execute(
                "SELECT message_id, disposition FROM messages "
                "WHERE quote_id = ? OR message_id IN "
                "(SELECT message_id FROM line_events WHERE quote_id = ?) "
                "ORDER BY timestamp",
                (quote_id, quote_id),
            ).fetchall()
            return {
                "quote_id": row["id"],
                "status": row["status"],
                "conversations": _conversations(conn, quote_id),
                "line_items": _lines(conn, quote_id),
                "history": [dict(h) for h in history],
                "messages": [dict(m) for m in messages],
            }

    @app.get("/review")
    def list_review():
        """The human-decision queue: messages we refused to guess about."""
        with get_db() as conn:
            rows = conn.execute(
                "SELECT * FROM pending_assignments WHERE status = 'pending' ORDER BY id"
            ).fetchall()
            return {
                "pending": [
                    {
                        "id": r["id"],
                        "message_id": r["message_id"],
                        "conversation_id": r["conversation_id"],
                        "text": r["text"],
                        "candidate_quote_ids": json.loads(r["candidate_quote_ids"]),
                        "reason": r["reason"],
                    }
                    for r in rows
                ]
            }

    @app.post("/review/{item_id}/resolve")
    def resolve_review(item_id: int, decision: ReviewResolveIn):
        """A person decides: 'apply' the cancel to the chosen quote, or discard.

        Guard rails worth showing in the review:
          - 404 unknown item, 409 already resolved (no double-apply);
          - 422 if quote_id isn't one of the candidates recorded when the
            message was parked — a human can only pick among the quotes the
            system said were plausible, and their pick is audited with the
            original message_id as cause.
        """
        with get_db() as conn:
            row = conn.execute(
                "SELECT * FROM pending_assignments WHERE id = ?", (item_id,)
            ).fetchone()
            if row is None:
                raise HTTPException(404, "No such review item")
            if row["status"] != "pending":
                raise HTTPException(409, "Already resolved")

            candidates = json.loads(row["candidate_quote_ids"])
            if decision.decision == "apply":
                if decision.quote_id not in candidates:
                    raise HTTPException(
                        422, f"quote_id must be one of {candidates}")
                conn.execute(
                    "UPDATE quotes SET status = 'cancelled' WHERE id = ?",
                    (decision.quote_id,),
                )
                conn.execute(
                    "INSERT INTO line_events (quote_id, sku, old_qty, new_qty, cause, message_id, timestamp) "
                    "VALUES (?, NULL, NULL, NULL, 'cancelled', ?, ?)",
                    (decision.quote_id, row["message_id"], _now()),
                )
                conn.execute(
                    "UPDATE messages SET disposition = 'cancelled', quote_id = ? "
                    "WHERE message_id = ?",
                    (decision.quote_id, row["message_id"]),
                )
            conn.execute(
                "UPDATE pending_assignments SET status = 'resolved', resolution = ?, "
                "resolved_quote_id = ? WHERE id = ?",
                (decision.decision, decision.quote_id, item_id),
            )
            return {"id": item_id, "status": "resolved",
                    "resolution": decision.decision}

    @app.post("/ingest/conversation")
    def ingest_conversation(payload: ConversationIn):
        """Phase 1: full conversation history -> one draft quote."""
        extraction = extract_conversation(
            [m.model_dump() for m in payload.conversation_history]
        )
        if not extraction.line_items:
            raise HTTPException(422, "No catalog line items could be extracted")
        with get_db() as conn:
            if payload.customer_name:
                conn.execute(
                    "INSERT OR IGNORE INTO customers (id, name) VALUES (?, ?)",
                    (payload.customer_id, payload.customer_name),
                )
            ensure_conversation(conn, payload.conversation_id, payload.customer_id)
            quote_id = create_quote(
                conn, payload.customer_id, payload.conversation_id,
                extraction.line_items, message_id=f"ingest-{payload.conversation_id}",
            )
            return {
                "document_type": "Oferta_de_Venta",
                "quote_id": quote_id,
                "status": "draft",
                "conversations": [payload.conversation_id],
                "line_items": extraction.line_items,
            }

    @app.post("/ingest/message")
    def ingest_message(payload: MessageIn):
        """Phase 2: one WhatsApp event at a time. Idempotent by message_id.

        Stateless handler on purpose: all state lives in SQLite (see db.py),
        so two app processes — or a restart between events — behave
        identically. The whole routing decision happens inside
        engine.process_message; see its docstring for the event-4 walkthrough.
        """
        with get_db() as conn:
            return process_message(conn, payload)

    return app


def _conversations(conn, quote_id: str) -> list[str]:
    rows = conn.execute(
        "SELECT conversation_id FROM quote_conversations WHERE quote_id = ? ORDER BY linked_at, conversation_id",
        (quote_id,),
    ).fetchall()
    return [r["conversation_id"] for r in rows]


def _lines(conn, quote_id: str) -> list[dict]:
    rows = conn.execute(
        "SELECT sku, qty FROM quote_lines WHERE quote_id = ? ORDER BY sku",
        (quote_id,),
    ).fetchall()
    return [{"sku": r["sku"], "qty": r["qty"]} for r in rows]


app = create_app()
