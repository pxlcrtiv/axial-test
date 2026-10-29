# 5: Extra credit — duplicate delivery idempotency

**What to build:** Re-posting a byte-identical event (same `message_id`) is a no-op: stored state unchanged, the message recorded with an `ignored-duplicate` disposition. Two different messages with the same text remain two real requests.

**Blocked by:** 3.

**Status:** ready-for-agent

- [ ] Re-send event 4 → final state identical (line qty still 4, no double-link, no extra line_event)
- [ ] Two distinct message_ids with identical text both apply
