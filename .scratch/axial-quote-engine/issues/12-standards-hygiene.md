# 12: Standards hygiene — audit helper + engine consolidation + extractor dedup

**What to build:** A behaviour-neutral cleanup pass: the duplicated audit-insert shape collapses into one helper; the `cancelled` transition moves from the route into the engine (whose docstring already claims it lives there); the extractor stops re-running normalize/correction and re-searching a quantity pattern it already has; `process_message` takes the message object instead of six travelling params; intent becomes a `Literal`; the dead `pending_mentions` field goes; `SKUS()` gets an honest name. Verifiable as: identical API behaviour, full suite green.

**Blocked by:** 9, 11 (same functions — batch after those land to avoid conflicts).

**Status:** done

- [x] One `_audit(...)` helper; no duplicated `INSERT INTO line_events` shape outside it
- [x] `cancelled` transition implemented in the engine, not the route
- [x] `extract_message` doesn't duplicate `_QTY_PATTERNS[1]` or re-normalize before delegating
- [x] `record_message` receives the payload object; intent is `Literal[...]`; `pending_mentions` removed; `SKUS()` renamed
- [x] Full suite green with zero behaviour change (13 tests)
