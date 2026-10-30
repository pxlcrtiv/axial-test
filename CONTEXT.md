# CONTEXT.md — Quote & State Engine

Domain glossary. Use these terms exactly in code, tests, issues, and docs;
don't drift to synonyms.

| Term | Meaning |
| --- | --- |
| **Oferta de Venta** | The sales quote document this system produces. Always starts in `draft` status; pricing is out of scope (the ERP prices it). |
| **Quote** | One `Oferta de Venta` row: id (`Q-NNN`), customer, status, line items. Knows nothing about which chats fed it. |
| **Line item** | A `(quote_id, sku, qty)` tuple. Only ever references its quote — never a conversation. |
| **Conversation** | One WhatsApp chat thread (`wa-thread-NNN`), identified independently of any quote. May feed many quotes. |
| **Link** | An observed `(quote, conversation)` pair in the junction table. Links are recorded *after* a message acts on a quote; they are never assumed upfront for routing. |
| **Disposition** | What happened to an ingested message: `created`, `updated`, `linked`, `noted`, `needs_review`, `ignored-duplicate`, `cancelled`. |
| **Candidate quote** | A quote that a message *could* refer to, computed from the product families the message references (within the message's customer). Routing acts only when exactly one candidate exists. |
| **Review queue / pending assignment** | An ambiguous message parked with its candidate quotes. State is frozen until a human resolves it (`apply` / `discard`); the resolution always stores `resolved_by` (the deciding identity — required, never defaulted). |
| **Resolver / actor** | The `resolved_by` identity on a review resolution: who/what made the call. Persisted with the outcome in `pending_assignments`, surfaced in `GET /review`'s `resolved` list. |
| **Family** | Coarse product class (`lona`, `mesh`, `microperforado`, `acrilico`) used by the extractor; maps to catalog SKUs via `app/catalog.py`. |
| **Catalog** | The four-SKU mock DB in `app/catalog.py`. The only source of valid SKU strings; foreign SKUs are impossible by construction. |

Key ADR-worthy decisions are recorded inline in code docstrings and the
README (junction data model, reference-based routing, no-LLM determinism);
see `docs/adr/` for decisions once recorded there.
