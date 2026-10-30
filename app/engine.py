"""State engine: applies extraction results and message intents to storage.

Transitions (each writes a line_events audit row + a messages disposition):

  create    -- new quote for a customer ("aparte", or the first request)
  update    -- a line's qty changes on an existing quote
  linked    -- a conversation joins a quote (event 2: link only, no line change)
  needs_review -- ambiguous ("mejor cancelalo"): parked, nothing changes
  ignored_duplicate -- same message_id seen before: no-op (webhook retry)

Routing rule (event 4's answer): a message is assigned by WHAT IT REFERENCES
(explicit product mention -> candidate quotes for that customer carrying the
family's SKU), never by which chat it arrived in. Exactly one candidate ->
apply. Several -> review queue. None -> create-new only if the message is a
fresh request, else review queue.
"""
import json
from datetime import datetime, timezone

from .catalog import CATALOG
from .db import get_db
from .extract import extract_message


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def next_quote_id(conn) -> str:
    row = conn.execute("SELECT MAX(id) AS m FROM quotes").fetchone()
    n = int(row["m"].split("-")[1]) + 1 if row and row["m"] else 1
    return f"Q-{n:03d}"


def ensure_conversation(conn, conversation_id: str, customer_id: str):
    conn.execute(
        "INSERT OR IGNORE INTO conversations (id, customer_id) VALUES (?, ?)",
        (conversation_id, customer_id),
    )


def link_conversation(conn, quote_id: str, conversation_id: str, message_id: str):
    """Add a (quote, conversation) pair to the many-to-many junction.

    INSERT OR IGNORE: re-linking is a no-op, so the junction has no
    duplicates and each NEW link gets exactly one 'linked' audit row.
    This is the only place conversations and quotes ever touch — neither
    table holds the other's id (see db.py schema header).
    """
    cur = conn.execute(
        "INSERT OR IGNORE INTO quote_conversations (quote_id, conversation_id, linked_at) "
        "VALUES (?, ?, ?)",
        (quote_id, conversation_id, _now()),
    )
    if cur.rowcount:  # genuinely new link -> audit it
        conn.execute(
            "INSERT INTO line_events (quote_id, sku, old_qty, new_qty, cause, message_id, timestamp) "
            "VALUES (?, NULL, NULL, NULL, 'linked', ?, ?)",
            (quote_id, message_id, _now()),
        )


def create_quote(conn, customer_id: str, conversation_id: str,
                 line_items: list[dict], message_id: str) -> str:
    quote_id = next_quote_id(conn)
    conn.execute(
        "INSERT INTO quotes (id, customer_id, status, created_at) VALUES (?, ?, 'draft', ?)",
        (quote_id, customer_id, _now()),
    )
    link_conversation(conn, quote_id, conversation_id, message_id)
    for li in line_items:
        conn.execute(
            "INSERT INTO quote_lines (quote_id, sku, qty) VALUES (?, ?, ?)",
            (quote_id, li["sku"], li["qty"]),
        )
        conn.execute(
            "INSERT INTO line_events (quote_id, sku, old_qty, new_qty, cause, message_id, timestamp) "
            "VALUES (?, ?, NULL, ?, 'created', ?, ?)",
            (quote_id, li["sku"], li["qty"], message_id, _now()),
        )
    return quote_id


def record_message(conn, message_id: str, conversation_id: str, customer_id: str,
                   direction: str, timestamp: str, text: str,
                   disposition: str, quote_id: str | None = None):
    conn.execute(
        "INSERT OR IGNORE INTO messages (message_id, conversation_id, customer_id, "
        "direction, timestamp, text, disposition, quote_id) VALUES (?,?,?,?,?,?,?,?)",
        (message_id, conversation_id, customer_id, direction, timestamp, text,
         disposition, quote_id),
    )


def is_duplicate(conn, message_id: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM messages WHERE message_id = ?", (message_id,)
    ).fetchone() is not None


# --------------------------------------------------------------------------
# Routing (Phase 2)
# --------------------------------------------------------------------------

def _family_skus(families: list[str]) -> set[str]:
    return {s.sku for s in CATALOG.values() if s.family in families}


def candidate_quotes(conn, customer_id: str, families: list[str]) -> list[str]:
    """Quotes this message could refer to, decided by WHAT it mentions.

    A quote is a candidate when one of its lines carries a SKU in one of the
    referenced product families. The arriving conversation is irrelevant —
    that's what makes event 4 (revision from the "wrong" chat) work.

    Both obvious shortcuts break on the four events; this function is why
    neither exists in the schema:
      - conversation->quote_id would hard-wire one chat to one quote and
        break event 3 ("aparte": Alice's chat starts Q-002);
      - quote->conversation_id would hard-wire one quote to one chat and
        break event 2 (Mario's chat joins Q-001).
    The junction table quote_conversations records every (quote, chat) pair
    the system has OBSERVED interacting, and this function ignores it when
    routing — reference decides, arrival only gets linked afterwards.
    """
    if not families:
        # no product reference: every open quote of this customer is a candidate
        # (e.g. "mejor cancelalo" -> all of them -> ambiguity is visible here)
        rows = conn.execute(
            "SELECT id FROM quotes WHERE customer_id = ? AND status = 'draft' ORDER BY id",
            (customer_id,),
        ).fetchall()
        return [r["id"] for r in rows]
    skus = _family_skus(families)
    if not skus:
        return []
    rows = conn.execute(
        "SELECT DISTINCT q.id FROM quotes q JOIN quote_lines l ON l.quote_id = q.id "
        "WHERE q.customer_id = ? AND q.status = 'draft' AND l.sku IN (%s) ORDER BY q.id"
        % ",".join("?" * len(skus)),
        (customer_id, *sorted(skus)),
    ).fetchall()
    return [r["id"] for r in rows]


def _update_line(conn, quote_id: str, sku: str, new_qty: int, message_id: str) -> bool:
    row = conn.execute(
        "SELECT qty FROM quote_lines WHERE quote_id = ? AND sku = ?",
        (quote_id, sku),
    ).fetchone()
    if row is None or row["qty"] == new_qty:
        return False
    conn.execute(
        "UPDATE quote_lines SET qty = ? WHERE quote_id = ? AND sku = ?",
        (new_qty, quote_id, sku),
    )
    conn.execute(
        "INSERT INTO line_events (quote_id, sku, old_qty, new_qty, cause, message_id, timestamp) "
        "VALUES (?, ?, ?, ?, 'updated', ?, ?)",
        (quote_id, sku, row["qty"], new_qty, message_id, _now()),
    )
    return True


def _park_review(conn, payload, families: list[str], candidates: list[str], reason: str):
    conn.execute(
        "INSERT INTO pending_assignments (message_id, conversation_id, customer_id, text, "
        "candidate_quote_ids, reason) VALUES (?,?,?,?,?,?)",
        (payload.message_id, payload.conversation_id, payload.customer_id,
         payload.text, json.dumps(candidates), reason),
    )


def process_message(conn, payload) -> dict:
    """Single ingest path for one WhatsApp event. Returns a disposition report.

    Order: dedupe -> extract intent -> route by reference -> apply or park.

    WALKTHROUGH OF EVENT 4 ("...y de los acrilicos que cotizó Alice, mejor
    que sean 4", arriving in Mario's chat wa-thread-662):

      1. is_duplicate? No — message_id wamid.662.0002 not in messages yet.
      2. extract_message -> intent="revise", families=["acrilico"], new_qty=4.
      3. candidate_quotes(customer=C-10029, families=["acrilico"]):
         quotes of THIS CUSTOMER whose lines carry an acrilico-family SKU.
         Only Q-002 does (Q-001 has lonas/mesh/microperforado).
         The arriving conversation wa-thread-662 is NEVER consulted here —
         that is exactly why a revision from the "wrong" chat still lands.
      4. Exactly one candidate -> apply: ARACBL-03 line 2 -> 4, audit row
         written with this message_id as the cause.
      5. link_conversation(Q-002, wa-thread-662): the junction now records
         that this chat also feeds Q-002 (state remembers the cross-link).
      6. record_message: disposition="updated", quote_id="Q-002".
    """
    # --- Step 1: idempotency. WhatsApp may re-deliver a webhook; message_id
    # is the primary key of `messages`, so a re-send short-circuits here
    # BEFORE any state changes. Dedupe is by id, never by text — two distinct
    # messages with identical wording are two real requests.
    if is_duplicate(conn, payload.message_id):
        # the row exists (INSERT OR IGNORE would be a no-op): update it so the
        # history shows the retry was seen and skipped, not the original story
        conn.execute(
            "UPDATE messages SET disposition = 'ignored-duplicate' WHERE message_id = ?",
            (payload.message_id,),
        )
        return {"message_id": payload.message_id, "disposition": "ignored-duplicate",
                "quote_id": None}

    # --- Step 2: deterministic intent extraction (no LLM). See extract.py.
    ensure_conversation(conn, payload.conversation_id, payload.customer_id)
    ex = extract_message(payload.text)

    # --- Step 3: WHO can this message refer to? Decided purely by WHAT it
    # references (product family -> quotes carrying that family's SKUs),
    # never by which chat it arrived in. See candidate_quotes() docstring.
    candidates = candidate_quotes(conn, payload.customer_id, ex.families)

    def _done(disposition: str, quote_id: str | None):
        """Persist the message's story (disposition + acting quote) and reply."""
        record_message(conn, payload.message_id, payload.conversation_id,
                       payload.customer_id, payload.direction, payload.timestamp,
                       payload.text, disposition, quote_id)
        return {"message_id": payload.message_id, "disposition": disposition,
                "quote_id": quote_id}

    # --- Step 4a: CANCEL is never guessed. With N open quotes it could mean
    # any of them -> park in the review queue with the candidate list; zero
    # rows in quotes/quote_lines change until a human calls /review/resolve.
    if ex.intent == "cancel":
        _park_review(conn, payload, ex.families, candidates, reason="ambiguous-cancel")
        return _done("needs_review", None)

    # --- Step 4b: REVISE. Zero candidates (nothing to revise) or >1 candidates
    # (genuinely ambiguous which quote) -> also park, never pick one at random.
    # Exactly one candidate -> apply the qty change + audit + cross-link.
    if ex.intent == "revise":
        if not candidates:
            _park_review(conn, payload, ex.families, [], reason="revision-no-target")
            return _done("needs_review", None)
        if len(candidates) > 1:
            _park_review(conn, payload, ex.families, candidates, reason="ambiguous-revision")
            return _done("needs_review", None)
        quote_id = candidates[0]
        changed = False
        # full (sku, qty) pairs found in the message take precedence...
        for li in ex.line_items:
            changed |= _update_line(conn, quote_id, li["sku"], li["qty"], payload.message_id)
        # ...otherwise a bare quantity ("sean 4") applies to the referenced
        # family's line on the single candidate quote (event 1 and event 4).
        if ex.new_qty is not None and not ex.line_items:
            for sku in sorted(_family_skus(ex.families)):
                if conn.execute("SELECT 1 FROM quote_lines WHERE quote_id=? AND sku=?",
                                (quote_id, sku)).fetchone():
                    changed |= _update_line(conn, quote_id, sku, ex.new_qty, payload.message_id)
        # arriving chat joins the quote it acted on: this is how wa-thread-662
        # ends up linked to BOTH quotes (event 2 links Q-001, event 4 Q-002)
        link_conversation(conn, quote_id, payload.conversation_id, payload.message_id)
        return _done("updated" if changed else "linked", quote_id)

    # --- Step 4c: QUESTION changes no quantities, but a new chat asking
    # about a quote should be remembered as connected to it (event 2).
    if ex.intent == "question":
        if len(candidates) == 1:
            link_conversation(conn, candidates[0], payload.conversation_id, payload.message_id)
            return _done("linked", candidates[0])
        if len(candidates) > 1:
            _park_review(conn, payload, ex.families, candidates, reason="ambiguous-question")
            return _done("needs_review", None)
        return _done("noted", None)  # question about nothing we track

    # --- Step 4d: CREATE ("aparte" = separate request) -> new quote in the
    # same chat. One conversation can feed any number of quotes (event 3).
    if ex.intent == "create" and ex.line_items:
        quote_id = create_quote(conn, payload.customer_id, payload.conversation_id,
                                ex.line_items, payload.message_id)
        return _done("created", quote_id)

    # --- Step 4e: recognized-as-nothing (greetings, acks): recorded, ignored.
    return _done("noted", None)
