# Quote & State Engine

Spec: Axial take-home assignment (48h timebox, ~6h active). Headless pipeline: WhatsApp conversation → structured `Oferta_de_Venta` draft quote → stays correct as messages keep arriving.

## Requirements (verbatim anchors)

- Phase 1: `POST` with `conversation_history` → draft quote with SKUs + qty (pricing out of scope).
- Phase 2: single-message ingest; four events in order; stored state correct after each; state survives process restart.
- Data model: no `quote_id` on conversation, no `conversation_id` on quote — many-to-many.
- History: a human can see what changed and which message caused it.
- Impossible to emit a SKU not in the catalog, by construction.
- Ambiguous message ("mejor cancelalo") → nothing changes until a human decides.
- Extra credit: dedupe by `message_id` (not text); implement the cancel-review queue.

## Catalog

| SKU | Description |
| --- | --- |
| ALFBTC-013-320100 | Lona Frontlit BTE 13 3.20x100 |
| ALMCLC-0909-320100 | Lona Mesh CLN 9x9 3.20x100 |
| AVMICS-1A-137050 | Vinil Adhesivo Microperforado 1.37x50 |
| ARACBL-03-122244 | Acrilico Blanco 3mm 1.22x2.44 |

## Settled decisions (grilling)

- Deterministic extraction (no LLM calls); `Extractor` seam documented for an LLM adapter.
- Python + FastAPI + Pydantic; SQLite on disk.
- Both extra credits in scope (dedupe in core ingest path; review queue as module).
- PR per phase; E2E replay of the assignment is the acceptance test.
