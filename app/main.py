"""Quote & State Engine — headless pipeline: WhatsApp conversation -> Oferta de Venta."""
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException

from .db import get_db, init_db
from .engine import create_quote, ensure_conversation, record_message
from .extract import extract_conversation
from .models import ConversationIn, QuotesOut


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
