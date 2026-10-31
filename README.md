# Quote & State Engine

Headless pipeline (FastAPI + SQLite): turns a colloquial WhatsApp conversation
into a structured `Oferta_de_Venta` draft quote, and keeps that quote correct as
messages keep arriving — revisions, questions from a second chat, and new
requests — without mixing them up. Pricing is out of scope: quotes carry SKUs
and quantities; the ERP prices them later.

## Run it

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app.main:app --port 8000      # API
.venv/bin/pytest                                 # 19 tests: 13 E2E + 6 structure checks
```

State lives in `quotes.db` (SQLite file, set `QUOTES_DB_PATH` to move it) — it
survives process restarts by construction.

### Endpoints

| Method | Path | What it does |
| --- | --- | --- |
| POST | `/ingest/conversation` | Phase 1: full conversation history → one draft quote |
| POST | `/ingest/message` | Phase 2: one WhatsApp event; idempotent by `message_id` |
| GET | `/quotes?customer=C-10029` | All quotes for a customer (final-state view) |
| GET | `/quotes/{id}` | One quote + audit history + per-message dispositions |
| GET | `/review` | Pending ambiguous messages awaiting a human |
| POST | `/review/{id}/resolve` | Human decision: `apply` (cancel chosen quote) or `discard` |

---

## 1. Data model

The two obvious shortcuts both break: a `quote_id` on the conversation breaks
event 3 (Alice's chat must feed *two* quotes), and a `conversation_id` on the
quote breaks event 2 (Mario's chat must join *an existing* quote). So neither
table holds the other's id — the connection is a **many-to-many junction**:

```
customers ──< conversations
     │              │
     │        quote_conversations        ← junction: every (quote, chat)
     │              │                        pair the system has OBSERVED
     └──< quotes >──┘                        interacting. Many-to-many.
             │
             └──< quote_lines (sku, qty)   ← no conversation reference, ever
             └──< line_events              ← audit: (quote, sku, old→new,
                                                cause, message_id)
     messages (message_id PK)              ← dedupe by primary key;
                                                disposition = what happened
     pending_assignments                   ← review queue for ambiguity
```

| Table | Key columns | Why it's shaped this way |
| --- | --- | --- |
| `quotes` | id, customer_id, status | No conversation id — a quote can be fed by any number of chats (event 2) |
| `conversations` | id, customer_id | No quote id — a chat can feed any number of quotes (event 3) |
| `quote_conversations` | (quote_id, conversation_id) PK | The junction absorbs both; links are *observed*, never *assumed* |
| `quote_lines` | (quote_id, sku) PK, qty | Lines know only their quote — routing can't accidentally depend on chat |
| `messages` | message_id PK, disposition, quote_id | Idempotency (webhook retries) + the per-message story |
| `line_events` | id, quote_id, sku?, old, new, cause, message_id | Append-only history: what changed **and which message caused it** |
| `pending_assignments` | candidates JSON, status | Parked ambiguity; nothing changes until a human resolves |

### How a new message finds its quote

`POST /ingest/message` → `engine.process_message()`:

1. **Dedupe.** `message_id` is the primary key of `messages`. Seen before →
   record `ignored-duplicate`, return. No state touched.
2. **Extract** (deterministic, no LLM): intent (`revise`/`create`/`question`/
   `cancel`), referenced product families, quantities.
3. **Candidate search — reference decides, arrival does not.**
   `candidate_quotes(customer, families)`: quotes of *this customer* whose
   lines carry a SKU in a referenced family. The arriving chat is never
   consulted at this step.
4. **Apply or park**, by count: exactly one candidate → act (qty update +
   audit row + link arriving chat to the quote); several or none → park in
   `pending_assignments`, change nothing.

**Event 4 walkthrough** ("…y de los acrilicos que cotizó Alice, mejor que sean
4", arriving in Mario's chat `wa-thread-662`):

1. `is_duplicate("wamid.662.0002")` → no.
2. `extract_message` → `intent="revise"`, `families=["acrilico"]`, `new_qty=4`.
3. `candidate_quotes("C-10029", ["acrilico"])` → quotes of C-10029 with an
   acrilico-family SKU on some line → only **Q-002** (Q-001 carries lonas,
   mesh, microperforado). `wa-thread-662` — the chat the message arrived in —
   is never consulted here.
4. One candidate → apply: `ARACBL-03` line 2 → 4, `line_events` row
   `(Q-002, ARACBL-03, 2, 4, updated, wamid.662.0002)`.
5. `link_conversation(Q-002, wa-thread-662)` — the junction records that this
   chat now also feeds Q-002 (this is how Q-002 ends up with both conversations).
6. Message stored: disposition `updated`, `quote_id=Q-002`.

The message said *which* quote it meant ("los acrilicos" → the quote holding
acrilicos); the chat only became linked *afterwards*, as a side effect of the
message acting on that quote.

## 2. What happens to a message we can't confidently assign?

It never guesses. A message like *"mejor cancelalo"* — two open quotes, no
product reference to discriminate — is matched against every open quote for
that customer, and the **whole set** is written to `pending_assignments`
alongside the original message text, chat, and `message_id`. Every downstream
table (`quotes`, `quote_lines`, `line_events`) is untouched: no quantity
changes, no status flips, no ERP push. The message becomes visible work
(`GET /review` shows the message plus its candidate quotes), and only a human
decision (`POST /review/{id}/resolve`) changes state — `apply` cancels exactly
the quote they chose (audited with the original message as cause; a non-candidate
quote id is rejected with 422), `discard` leaves everything as it was. A wrong
guess is cheap to fix only if it hasn't happened yet; a cancelled quote the
customer was still expecting is the wrong answer pushed into the ERP, so the
system's failure mode is *waiting*, not *acting*.

## 3. Deterministic vs. model call

There is **no LLM call in this build** — deliberately. The catalog has four
SKUs, the phrasing is bounded Spanish order-speak, and the evaluation explicitly
values not burning tokens on simple tasks. The table below holds for rules *or*
a model:

| Stage | What it decides | What it must never decide | If it's wrong |
| --- | --- | --- | --- |
| `extract_message` / `extract_conversation` (rules today; **the LLM seam**) | intent, quantities, product family, width | the SKU string itself | Wrong intent parks the message in review (safe); wrong qty produces a visible audit row a human reverts |
| `_match_sku` → `app.catalog` | — (pure lookup) | — | Can't be wrong: only returns catalog entries; unknown text returns `None` → no line |
| Pydantic `LineItem.sku` validator | — (boundary check) | — | Foreign SKU → 422 before storage; hallucination impossible by construction |
| `candidate_quotes` (SQL, deterministic) | which quotes *could* be meant | which one *is* meant (never picks among N>1) | Ambiguity → review queue, zero mutations |
| `engine.process_message` (SQL, deterministic) | applying the decision, audit | resolving ambiguity | N/A — ambiguity exits to the human |
| Human via `/review/{id}/resolve` | ambiguous finals (cancel among N quotes) | — | Guard rails: only recorded candidates (422 otherwise), no double-apply (409), fully audited |

Where the rules give up (→ to whom): unmatched phrasing or ambiguous
reference → `pending_assignments` → a human. The rules' `None` returns are the
handoff points.

## 4. Edge cases

| Case | What the system does | Why |
| --- | --- | --- |
| Webhook re-delivery of event 4 (same `message_id`, byte-identical) | `ignored-duplicate`, zero state change | `messages.message_id` is the PK; dedupe before routing |
| Two *different* messages, identical text | Both apply (second is a real repeat request) | Dedupe is by id, never by text — text-equality would swallow genuine repeats |
| "mejor cancelalo", 2 open quotes | Parked in review with candidates `[Q-001, Q-002]`; nothing changes | Ambiguity is a human decision (§2) |
| Resolve stores who decided | `resolved_by` is **required** on `/review/{id}/resolve` (422 if missing), persisted with the outcome, exposed in `GET /review`'s `resolved` list **and** joined onto `GET /quotes/{id}`'s `history` (the `cancelled` event carries it; machine transitions omit the key) | The audit must always answer "who/what decided" — a defaulted identity would make the answer a lie |
| Webhook redelivery after first ingestion | The message row's disposition flips to `ignored-duplicate`, quotes untouched | Retrying is *visible* — a human reading the history sees the skip, not a stale original story |
| "…mejor que sean 15, y también…" (revision + connective) | Routes as a revision; does not fork a new quote | Intent precedence: cancel > explicit "aparte" > question > revision > weak connectives (`tambien`/`agrega`) |
| Customer asks about 1.50 m width (not in catalog) | Mention yields no SKU → no line, no error | `_match_sku` returns `None` for widths the catalog doesn't carry |
| "lonas 15" — quantity *after* the family, no width | No line: `_QTY_PATTERNS` reads number-before-unit ("15 lonas"), so no qty pairs with the mention; nothing is created, and a later "mejor que sean 10" parks as `revision-no-target` (verified: two messages, zero quotes) | Word-order sensitivity is the deterministic trade-off — guessing a qty (or a SKU) from an ambiguous phrase is exactly what the catalog forbids. Note the SKU *would* resolve (each family has one SKU today); the qty is what's missing |
| Second chat asks "qué lleva la cotización" (event 2) | Link `wa-thread-662` → Q-001, quantities untouched | Questions reference, never mutate; junction records the observed link |
| "aparte" in a chat that already has a quote (event 3) | New quote Q-002, same chat linked to both | No conversation→quote FK exists to break |
| Revision targets a family no open quote carries | Parked (`revision-no-target`), nothing changes | Nothing to revise ≠ create-new; guessing would fork the quote tree |
| **Deliberately not handled: concurrent writes to the same quote** | Last-writer-wins within SQLite's default locking | Two humans revising one line simultaneously is a real conflict; correct handling needs row-level versioning or Postgres `SELECT … FOR UPDATE` — out of 80/20 scope for a single-writer demo |
| **Deliberately not handled: multi-item revisions in one message** ("lonas 15 y mesh 8") | Only the first matched family routes the message | The brief's messages revise one thing at a time; multi-target revision needs a per-family candidate split — an honest gap, not a silent one: today's behavior would park it as ambiguous |

## 5. Architectural trade-offs & scaling to 1,000 conversations/day

**Kept by design** (reviewed, deliberate API choices — not silent gaps):
`POST /ingest/conversation` returns **422** when *no* catalog line item can be
extracted — a quote document with nothing in it is not a useful resource, and
silently creating an empty draft would pollute the ERP hand-off; the
`customers` table + optional `customer_name` on the Phase-1 payload exist so
quotes are attributable to a real contact — both go slightly beyond the brief
on purpose.

**Chosen:** deterministic extraction + SQL routing + SQLite file. Rejected
alternatives: an LLM in the hot path (cost, non-determinism, and it still
couldn't name a SKU outside the catalog — so it would buy paraphrase-robustness
only, at the price of reproducible demos); a rules-engine framework (a hand-rolled
intent classifier with 4 intents fits on one screen); Postgres (nothing here
needs it yet).

**What I'd change first with another week:** paraphrase robustness — a
constrained LLM adapter behind the existing `extract_message` seam (enum-constrained
intent + catalog-enum SKUs), with the deterministic parser as the fast path and
the model only for `intent="none"` messages that still contain catalog keywords.
Then: a webhook ingress with retry/backoff, and multi-item revision splitting.

**What I'd rip out first:** the positional `Q-{n:03d}` id allocation
(`MAX(id)+1`) — it's fine single-writer and demo-grade, but it's the first
thing to break under concurrency. Replace with an allocation table or
ULID-on-insert.

**Scale to 1,000 conversations/day** (< 1/minute): what actually breaks first
is *not* throughput — it's SQLite's single-writer lock during bursty webhook
retries, then the single-process FastAPI deployment. In order:
(1) `PRAGMA journal_mode=WAL` + short transactions (trivial, likely enough for
a year at this rate); (2) a queue between webhook and ingest to serialize
writes per customer; (3) Postgres when multiple app instances or concurrent
revision of the same quote become real — the schema port's only change is the
junction/PK types. Read traffic (`GET /quotes`) scales first with a read replica
or cached projections; extraction is microseconds and never a bottleneck.

## 6. How I used AI tools

Honestly and heavily, I used a coding agent (OpenCode), the way the take-home
assumes. The workflow was: grill the design decisions first (stack, storage,
dedupe/queue scope, PR slicing), write the tickets, then **test-first**: every
slice began with a failing E2E test that replays the assignment verbatim, so
the model's code had to satisfy byte-exact expected output, not a prose
reading of it. AI wrote the code; the deterministic design decisions (junction
model, reference-based routing, catalog-only SKU path, dedupe-before-route)
were made consciously in review, not discovered by accident. What AI did *not*
do: silently accept passing tests — the Phase 1 extractor's first clause-ordering
draft and an over-narrow audit assertion were both caught by reading the
diff, not by green tests alone. The README's claims are grounded in the code
they describe; everything in this file is verifiable with `.venv/bin/pytest`.

Two honesty notes about this repo's own history:

1. **A debug log was committed early and stays in old commits.** A
   `firebase-debug.log` (containing a personal email address) landed in the
   first commits and was untracked in PR #5 — but it is *still reachable in
   git history*, which was deliberately left untouched rather than
   force-pushed (rewriting pushed history is a destructive operation).
   Fresh checkouts don't contain the file (`*.log` is gitignored and the
   tree is clean); only old commits carry it.
2. **Clean-checkout claim, re-verified.** From a true `git clone` of this
   repo into an empty directory: no `*.log` files present,
   `pip install -r requirements.txt && pytest` → **19 passed**.

---

## API examples

```bash
# Phase 1: conversation -> draft quote
curl -s localhost:8000/ingest/conversation -H 'content-type: application/json' -d @phase1.json

# Phase 2: one event at a time
curl -s localhost:8000/ingest/message -H 'content-type: application/json' \
  -d '{"message_id":"wamid.411.0231","conversation_id":"wa-thread-411",
       "customer_id":"C-10029","direction":"inbound",
       "timestamp":"2026-02-11T10:14:00Z",
       "text":"Oye de las lonas mejor que sean 15, no 20"}'

# Final state
curl -s 'localhost:8000/quotes?customer=C-10029'

# Ambiguity queue (e.g. "mejor cancelalo")
curl -s localhost:8000/review
curl -s localhost:8000/review/1/resolve -H 'content-type: application/json' \
  -d '{"decision":"apply","quote_id":"Q-002","resolved_by":"izzy@acme"}'
```
