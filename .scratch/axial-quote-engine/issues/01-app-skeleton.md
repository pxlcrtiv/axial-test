# 1: App skeleton: catalog, schema, empty quotes endpoint

**What to build:** The API boots with the SQLite schema created on startup, the catalog loaded as the single source of SKU truth, and a Pydantic layer where a payload carrying a SKU outside the catalog is rejected (422) — impossible to persist a hallucinated SKU by construction. `GET /quotes?customer=C-10029` answers with an empty quote list.

**Blocked by:** None (can start immediately).

**Status:** ready-for-agent

- [ ] FastAPI app starts; SQLite DB file created with full schema (customers, conversations, quotes, quote_conversations junction, quote_lines, messages, line_events, pending_assignments)
- [ ] Catalog module exposes the 4 SKUs and a lookup; models validate SKUs against it
- [ ] `GET /quotes?customer=…` returns `{"quotes": []}` for an unknown customer
- [ ] E2E test: boot + empty quotes + invalid-SKU 422, all green
