# 4: Audit trail — what changed and which message caused it

**What to build:** Every state mutation records a `line_events` row (quote, SKU, old qty → new qty, message_id, timestamp). `GET /quotes/{id}` returns the quote with its history and per-message dispositions, so a human can see that the 20→15 change was caused by `wamid.411.0231`.

**Blocked by:** 3.

**Status:** ready-for-agent

- [ ] After the four events, Q-001's history attributes the 20→15 change to `wamid.411.0231`
- [ ] `GET /quotes/{id}` includes line_events and message dispositions (created/updated/linked)
- [ ] Link-only and create transitions also appear in history
