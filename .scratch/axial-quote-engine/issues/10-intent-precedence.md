# 10: Fix intent collision — "tambien" misroutes revise to create

**What to build:** A message that revises an existing quote but also contains "también" (or similar connective) must not be classified as a fresh separate request. Intent precedence decides by structure — an explicit revision signal over an existing family wins — not by a single keyword match order. Genuine separate requests ("aparte cotizame N…") still create new quotes.

**Blocked by:** None (can start immediately).

**Status:** done

- [x] Red test: a revision phrasing containing "también" updates an existing line and does NOT fork a new quote
- [x] Event 3's "aparte" still creates Q-002 (existing test stays green)
- [x] Full suite green
