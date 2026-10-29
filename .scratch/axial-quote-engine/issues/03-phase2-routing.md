# 3: Phase 2 core — single-message ingest with quote routing

**What to build:** `POST /ingest/message` processes one WhatsApp event at a time. Replaying the assignment's four events in order yields the exact expected final state: (1) lona line 20→15 in Q-001, nothing else; (2) new chat wa-thread-662 linked to Q-001, no line changes; (3) "aparte" creates Q-002 (2× ARACBL-03) from Alice's chat; (4) from Mario's chat, Q-002's acrilico line → 4, and wa-thread-662 links to Q-002. Routing is by what the message references, never by which chat it arrived in.

**Blocked by:** 2.

**Status:** ready-for-agent

- [ ] Replaying events 1–4 → `GET /quotes?customer=C-10029` returns the expected final JSON (Q-001 with 15/5/5 and both conversations; Q-002 with qty 4 and both conversations)
- [ ] Event 2 performs a link-only transition; event 3 performs a create transition; no workarounds in the data model
- [ ] A revision arriving from a second chat applies to the referenced quote (event 4)
