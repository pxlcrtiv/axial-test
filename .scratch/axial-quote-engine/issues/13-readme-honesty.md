# 13: README honesty pass + glossary sync

**What to build:** The README's edge-case table and related sections match the final code exactly: the widthless-family routing gap is documented (a "lonas 15" message with no width can't pin a SKU and therefore can't route for revision — why, and what a human sees); the kept-by-design API choices (422 on conversations with zero extractable items, `customers` table) are stated as deliberate, not left as silent gaps; the clean-checkout claim is re-verified after ticket 8; CONTEXT.md picks up any vocabulary ticket 11 introduced (e.g. resolver/actor).

**Blocked by:** 8, 9, 10, 11 (must document the final behaviour).

**Status:** done

- [x] Widthless-family case in the edge table with mechanism + human-visible outcome
- [x] Kept-by-design items explicitly marked as such
- [x] Clean-checkout verification re-run and true
- [x] CONTEXT.md glossary consistent with new terms
