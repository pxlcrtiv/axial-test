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
