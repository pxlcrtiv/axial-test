# 13: README honesty pass + glossary sync

**What to build:** The README's edge-case table and related sections match the final code exactly: the no-width routing gap is documented (a "lonas 15" message extracts no quantity — `_QTY_PATTERNS` reads number-before-unit — so no line is created and a later revision parks as `revision-no-target`; the SKU itself *would* resolve, since each family has one SKU; corrected 2026-10-30 after review found the original "can't pin a SKU" wording factually wrong); the kept-by-design API choices (422 on conversations with zero extractable items, `customers` table) are stated as deliberate, not left as silent gaps; the clean-checkout claim is re-verified after ticket 8; CONTEXT.md picks up any vocabulary ticket 11 introduced (e.g. resolver/actor).

**Blocked by:** 8, 9, 10, 11 (must document the final behaviour).

**Status:** resolved

- [x] Widthless-family case in the edge table with mechanism + human-visible outcome
- [x] Kept-by-design items explicitly marked as such
- [x] Clean-checkout verification re-run and true
- [x] CONTEXT.md glossary consistent with new terms
