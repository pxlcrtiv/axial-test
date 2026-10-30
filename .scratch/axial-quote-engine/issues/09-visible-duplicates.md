# 9: Make duplicate delivery visible to a human

**What to build:** When a webhook re-delivery (same `message_id`) arrives, `GET /quotes/{id}` shows that message with disposition `ignored-duplicate` — a human can see the retry was seen and skipped, rather than the record silently keeping the original disposition. State still does not change (already covered by an existing test).

**Blocked by:** None (can start immediately).

**Status:** done

- [x] Red test: re-send an already-ingested event, then its message row reports `ignored-duplicate` while quotes are byte-identical
- [x] First ingestion still reports its real disposition (`updated`, `created`, …)
- [x] Full suite green
