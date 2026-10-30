# 11: Record who resolved a review item

**What to build:** `POST /review/{id}/resolve` captures the deciding actor and persists it with the resolution, so the audit answers "who/what decided" for every parked ambiguity — not just what was decided.

**Blocked by:** None (can start immediately).

**Status:** ready-for-agent

- [ ] Red test: resolve with an actor identity; the stored resolution exposes it (review/quote history)
- [ ] Missing actor is rejected or explicitly defaulted — the choice is stated in the README
- [ ] Full suite green
