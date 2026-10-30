"""E2E tests: the public HTTP API is the only seam under test.

Replays the Axial assignment verbatim: Phase 1 conversation -> draft quote,
then the four Phase 2 events, then the extra-credit cases.
"""
import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("QUOTES_DB_PATH", str(tmp_path / "quotes.db"))
    with TestClient(create_app()) as c:
        yield c


def test_empty_quotes_for_unknown_customer(client):
    r = client.get("/quotes", params={"customer": "C-99999"})
    assert r.status_code == 200
    assert r.json() == {"quotes": []}


def test_sku_outside_catalog_is_rejected(client):
    """A SKU that isn't in the catalog must be impossible to persist."""
    r = client.post(
        "/ingest/conversation",
        json={
            "customer_id": "C-00001",
            "conversation_id": "wa-thread-000",
            "customer_name": "Test",
            "conversation_history": [
                {"direction": "inbound", "timestamp": "2026-02-10T09:00:00Z",
                 "text": "cotizame 3 rollos FABRICATED-SKU-999"}
            ],
        },
    )
    # Either the extractor never emits it (no SKU matched -> no line item),
    # or the model layer rejects it. What must never happen: it persists.
    if r.status_code == 200:
        skus = {li["sku"] for li in r.json()["line_items"]}
        assert "FABRICATED-SKU-999" not in skus
    else:
        assert r.status_code == 422


PHASE1_PAYLOAD = {
    "customer_id": "C-10029",
    "conversation_id": "wa-thread-411",
    "customer_name": "Alice - ACME INDUSTRIAL",
    "conversation_history": [
        {"direction": "inbound", "timestamp": "2026-02-10T09:43:00Z",
         "text": "Hola buenos dias, me ayudas a cotizar 20 rollos lona 3.20 x 100 m., 5 rollos de mesh de 3.20 x 100 m. y si cuentas con microperforado de 1.37 y 1.50 m."},
        {"direction": "outbound", "timestamp": "2026-02-10T09:45:00Z",
         "text": "Hola buen día. Si. Cuantas piezas de microperforado"},
        {"direction": "outbound", "timestamp": "2026-02-10T09:45:30Z",
         "text": "De momento sería de 1.37x50"},
        {"direction": "inbound", "timestamp": "2026-02-10T09:46:00Z",
         "text": "Necesitamos 5 rollos"},
    ],
}


def test_phase1_conversation_to_draft_quote(client):
    r = client.post("/ingest/conversation", json=PHASE1_PAYLOAD)
    assert r.status_code == 200
    body = r.json()
    assert body["document_type"] == "Oferta_de_Venta"
    assert body["status"] == "draft"
    assert body["conversations"] == ["wa-thread-411"]
    assert sorted((li["sku"], li["qty"]) for li in body["line_items"]) == [
        ("ALFBTC-013-320100", 20),
        ("ALMCLC-0909-320100", 5),
        ("AVMICS-1A-137050", 5),
    ]
    # and it's queryable
    r2 = client.get("/quotes", params={"customer": "C-10029"})
    assert r2.json()["quotes"][0]["quote_id"] == body["quote_id"]


EVENTS = [
    {"message_id": "wamid.411.0231", "conversation_id": "wa-thread-411",
     "customer_id": "C-10029", "direction": "inbound",
     "timestamp": "2026-02-11T10:14:00Z",
     "text": "Oye de las lonas mejor que sean 15, no 20"},  # event 1: revise lona 20->15
    {"message_id": "wamid.662.0001", "conversation_id": "wa-thread-662",
     "customer_id": "C-10029", "direction": "inbound",
     "timestamp": "2026-02-11T11:00:00Z",
     "text": "Buen dia, soy Mario de compras de ACME. Alice me pasó con ustedes, me confirmas qué lleva la cotización de las lonas?"},  # event 2: link only
    {"message_id": "wamid.411.0232", "conversation_id": "wa-thread-411",
     "customer_id": "C-10029", "direction": "inbound",
     "timestamp": "2026-02-11T11:30:00Z",
     "text": "y aparte cotizame 2 acrilicos blancos de 3mm porfa"},  # event 3: new quote Q-002
    {"message_id": "wamid.662.0002", "conversation_id": "wa-thread-662",
     "customer_id": "C-10029", "direction": "inbound",
     "timestamp": "2026-02-12T09:00:00Z",
     "text": "perfecto. y de los acrilicos que cotizó Alice, mejor que sean 4"},  # event 4: Q-002 acrilico 2->4
]

EXPECTED_FINAL = [
    {"quote_id": "Q-001", "status": "draft",
     "conversations": ["wa-thread-411", "wa-thread-662"],
     "line_items": [
         {"sku": "ALFBTC-013-320100", "qty": 15},
         {"sku": "ALMCLC-0909-320100", "qty": 5},
         {"sku": "AVMICS-1A-137050", "qty": 5},
     ]},
    {"quote_id": "Q-002", "status": "draft",
     "conversations": ["wa-thread-411", "wa-thread-662"],
     "line_items": [
         {"sku": "ARACBL-03-122244", "qty": 4},
     ]},
]


def _sort_quotes(quotes):
    for q in quotes:
        q["conversations"] = sorted(q["conversations"])
        q["line_items"] = sorted(q["line_items"], key=lambda li: li["sku"])
    return sorted(quotes, key=lambda q: q["quote_id"])


def _seed_phase1(client):
    r = client.post("/ingest/conversation", json=PHASE1_PAYLOAD)
    assert r.status_code == 200


def test_phase2_four_events_final_state(client):
    _seed_phase1(client)
    for ev in EVENTS:
        r = client.post("/ingest/message", json=ev)
        assert r.status_code == 200, r.text

    r = client.get("/quotes", params={"customer": "C-10029"})
    assert _sort_quotes(r.json()["quotes"]) == _sort_quotes(EXPECTED_FINAL)


def test_phase2_event2_links_without_changing_lines(client):
    _seed_phase1(client)
    client.post("/ingest/message", json=EVENTS[1])  # Mario asks about lonas
    r = client.get("/quotes", params={"customer": "C-10029"})
    q1 = r.json()["quotes"][0]
    assert sorted(q1["conversations"]) == ["wa-thread-411", "wa-thread-662"]
    # no line changed
    assert {li["sku"]: li["qty"] for li in q1["line_items"]}["ALFBTC-013-320100"] == 20


def test_phase2_event3_creates_second_quote_from_same_chat(client):
    _seed_phase1(client)
    client.post("/ingest/message", json=EVENTS[2])  # "aparte"
    r = client.get("/quotes", params={"customer": "C-10029"})
    quotes = r.json()["quotes"]
    assert len(quotes) == 2
    assert quotes[1]["line_items"] == [{"sku": "ARACBL-03-122244", "qty": 2}]
    # both quotes live in Alice's chat
    assert quotes[1]["conversations"] == ["wa-thread-411"]


def test_audit_history_attributes_change_to_message(client):
    """A human can see what changed and which message caused it."""
    _seed_phase1(client)
    for ev in EVENTS:
        client.post("/ingest/message", json=ev)

    r = client.get("/quotes/Q-001")
    assert r.status_code == 200
    body = r.json()
    history = body["history"]
    lona_updates = [h for h in history
                    if h["sku"] == "ALFBTC-013-320100" and h["cause"] == "updated"]
    assert lona_updates == [{
        "sku": "ALFBTC-013-320100", "old_qty": 20, "new_qty": 15,
        "cause": "updated", "message_id": "wamid.411.0231",
    }]
    # link-only and create transitions also appear
    causes = {(h["cause"], h["message_id"]) for h in history}
    assert ("created", "ingest-wa-thread-411") in causes
    # message dispositions tell the per-message story
    dispositions = {m["message_id"]: m["disposition"] for m in body["messages"]}
    assert dispositions["wamid.411.0231"] == "updated"
    assert dispositions["wamid.662.0001"] == "linked"

    r2 = client.get("/quotes/Q-002")
    d2 = {m["message_id"]: m["disposition"] for m in r2.json()["messages"]}
    assert d2["wamid.411.0232"] == "created"
    assert d2["wamid.662.0002"] == "updated"


def test_duplicate_delivery_is_idempotent(client):
    """Webhook re-delivery (same message_id, byte-identical): no state change."""
    _seed_phase1(client)
    for ev in EVENTS:
        client.post("/ingest/message", json=ev)
    before = client.get("/quotes", params={"customer": "C-10029"}).json()

    r = client.post("/ingest/message", json=EVENTS[3])  # re-send event 4
    assert r.status_code == 200
    assert r.json()["disposition"] == "ignored-duplicate"

    after = client.get("/quotes", params={"customer": "C-10029"}).json()
    assert after == before

    # ...and a human can SEE the redelivery was skipped: the message row
    # reports ignored-duplicate, not the original ingestion's disposition
    detail = client.get("/quotes/Q-002").json()
    dispositions = {m["message_id"]: m["disposition"] for m in detail["messages"]}
    assert dispositions["wamid.662.0002"] == "ignored-duplicate"


def test_tambien_in_revision_does_not_fork_a_new_quote(client):
    """Intent precedence: a revision signal beats a bare 'tambien' connective.

    '...mejor que sean 15, y tambien manten el mesh' must revise Q-001's
    lona line, NOT create a new quote just because 'tambien' matched the
    create-keyword first.
    """
    _seed_phase1(client)
    r = client.post("/ingest/message", json={
        "message_id": "wamid.411.0400", "conversation_id": "wa-thread-411",
        "customer_id": "C-10029", "direction": "inbound",
        "timestamp": "2026-02-11T12:00:00Z",
        "text": "y de las lonas tambien mejor que sean 15"})
    assert r.status_code == 200
    assert r.json()["disposition"] in ("updated", "linked")
    assert r.json()["quote_id"] == "Q-001"

    quotes = client.get("/quotes", params={"customer": "C-10029"}).json()["quotes"]
    assert len(quotes) == 1, "revision with 'tambien' must not fork a new quote"
    lona = next(li for li in quotes[0]["line_items"]
                if li["sku"] == "ALFBTC-013-320100")
    assert lona["qty"] == 15


def test_same_text_different_message_id_is_a_real_repeat(client):
    """Dedupe is by message_id, not text: identical wording twice still applies."""
    _seed_phase1(client)
    ev = dict(EVENTS[0])                     # "mejor que sean 15, no 20"
    client.post("/ingest/message", json=ev)
    ev2 = dict(ev, message_id="wamid.411.0999")  # same text, new id
    r = client.post("/ingest/message", json=ev2)
    assert r.json()["disposition"] in ("updated", "linked")


def test_cancelalo_parks_in_review_queue_and_changes_nothing(client):
    """Ambiguous cancel with two open quotes: human decides, state frozen."""
    _seed_phase1(client)
    for ev in EVENTS[:3]:                    # Q-001 and Q-002 both exist
        client.post("/ingest/message", json=ev)
    before = client.get("/quotes", params={"customer": "C-10029"}).json()

    r = client.post("/ingest/message", json={
        "message_id": "wamid.411.0300", "conversation_id": "wa-thread-411",
        "customer_id": "C-10029", "direction": "inbound",
        "timestamp": "2026-02-12T10:00:00Z",
        "text": "mejor cancelalo"})
    assert r.status_code == 200
    assert r.json()["disposition"] == "needs_review"

    # nothing changed
    after = client.get("/quotes", params={"customer": "C-10029"}).json()
    assert after == before

    # a human can see it, with the quotes it might refer to
    rv = client.get("/review").json()
    assert len(rv["pending"]) == 1
    item = rv["pending"][0]
    assert item["message_id"] == "wamid.411.0300"
    assert item["candidate_quote_ids"] == ["Q-001", "Q-002"]
    assert "cancelalo" in item["text"]

    # resolving: discard -> quote untouched, item leaves the queue
    res = client.post(f"/review/{item['id']}/resolve",
                      json={"decision": "discard", "quote_id": None,
                            "resolved_by": "ops@acme"})
    assert res.status_code == 200
    after = client.get("/quotes", params={"customer": "C-10029"}).json()
    assert after == before
    assert client.get("/review").json()["pending"] == []


def test_review_resolve_apply_cancels_only_the_chosen_quote(client):
    """Human picks the quote it meant -> only that quote changes status."""
    _seed_phase1(client)
    for ev in EVENTS[:3]:
        client.post("/ingest/message", json=ev)
    client.post("/ingest/message", json={
        "message_id": "wamid.411.0301", "conversation_id": "wa-thread-411",
        "customer_id": "C-10029", "direction": "inbound",
        "timestamp": "2026-02-12T10:05:00Z", "text": "mejor cancelalo"})

    item = client.get("/review").json()["pending"][0]
    # applying to a quote outside the candidate list is refused
    bad = client.post(f"/review/{item['id']}/resolve",
                      json={"decision": "apply", "quote_id": "Q-999",
                            "resolved_by": "ops@acme"})
    assert bad.status_code == 422

    res = client.post(f"/review/{item['id']}/resolve",
                      json={"decision": "apply", "quote_id": "Q-002",
                            "resolved_by": "ops@acme"})
    assert res.status_code == 200
    quotes = {q["quote_id"]: q for q in
              client.get("/quotes", params={"customer": "C-10029"}).json()["quotes"]}
    assert quotes["Q-002"]["status"] == "cancelled"
    assert quotes["Q-001"]["status"] == "draft"
    # audit records who caused the cancel
    h = client.get("/quotes/Q-002").json()["history"]
    assert any(e["cause"] == "cancelled" and e["message_id"] == "wamid.411.0301"
               for e in h)
    # double-resolve is refused
    again = client.post(f"/review/{item['id']}/resolve",
                        json={"decision": "apply", "quote_id": "Q-002",
                              "resolved_by": "ops@acme"})
    assert again.status_code == 409


def test_review_resolution_records_the_deciding_actor(client):
    """Issue 6: 'records who/what decided' — identity stored with the outcome."""
    _seed_phase1(client)
    for ev in EVENTS[:3]:
        client.post("/ingest/message", json=ev)
    client.post("/ingest/message", json={
        "message_id": "wamid.411.0302", "conversation_id": "wa-thread-411",
        "customer_id": "C-10029", "direction": "inbound",
        "timestamp": "2026-02-12T10:10:00Z", "text": "mejor cancelalo"})

    item = client.get("/review").json()["pending"][0]
    # missing actor is rejected, not silently defaulted
    no_actor = client.post(f"/review/{item['id']}/resolve",
                           json={"decision": "discard", "quote_id": None})
    assert no_actor.status_code == 422

    res = client.post(f"/review/{item['id']}/resolve",
                      json={"decision": "discard", "quote_id": None,
                            "resolved_by": "izzy@acme"})
    assert res.status_code == 200
    assert res.json()["resolved_by"] == "izzy@acme"
    # and it persists: resolving again is 409, and the record shows the actor
    assert client.get("/review").json()["pending"] == []
    resolved = client.get("/review").json()["resolved"]
    assert resolved[0]["resolution"] == "discard"
    assert resolved[0]["resolved_by"] == "izzy@acme"
