# 6: Extra credit — "mejor cancelalo" review queue

**What to build:** A message whose intent is ambiguous (cancel/revise with several candidate quotes) creates a pending-assignment row naming the candidates and changes nothing. `GET /review` lists pending items; `POST /review/{id}/resolve` applies the human's decision (or discards) and records it.

**Blocked by:** 3.

**Status:** ready-for-agent

- [ ] With both quotes open, "mejor cancelalo" → queue entry naming Q-001 and Q-002; both quotes untouched
- [ ] `GET /review` lists it; resolving applies the decision and records who/what decided
- [ ] Resolved items leave the pending list
