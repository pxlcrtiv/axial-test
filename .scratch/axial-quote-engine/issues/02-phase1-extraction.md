# 2: Phase 1 — conversation history to draft quote

**What to build:** `POST /ingest/conversation` accepts the assignment's Phase 1 payload (customer + full `conversation_history`, both directions) and returns the expected draft quote JSON: `Oferta_de_Venta`, `status: draft`, three line items (lona 20, mesh 5, microperforado 5). The deterministic Spanish extractor assembles line items whose details are scattered across messages (product in one, size clarified by the rep in another, quantity in a third) and ignores what the catalog can't price (the 1.50 m width mention).

**Blocked by:** 1.

**Status:** ready-for-agent

- [ ] Extractor parses quantities, product mentions (family + dimensions), both directions, linearly with pending-mention state
- [ ] Catalog matcher maps "lona 3.20x100" → ALFBTC-013-320100, "mesh 3.20x100" → ALMCLC-0909-320100, "microperforado 1.37x50" → AVMICS-1A-137050; unmappable widths dropped
- [ ] E2E: assignment Phase 1 input → expected Q-001 output, exact line items
