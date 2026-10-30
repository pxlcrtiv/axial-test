"""Ticket 12: structural hygiene — behaviour-neutral, verified by shape."""
import inspect
import re
from typing import get_args, get_origin, Literal, Union

import app.engine as engine
import app.extract as extract
import app.main as main


def test_single_audit_helper_inserts_line_events():
    """The INSERT INTO line_events shape lives in one helper, not 4 copies."""
    sources = [inspect.getsource(engine), inspect.getsource(main)]
    inserts = sum(
        len(re.findall(r"INSERT INTO line_events", src)) for src in sources
    )
    assert inserts == 1, "audit insert must be written exactly once (the helper)"
    assert hasattr(engine, "_audit")


def test_cancelled_transition_lives_in_the_engine():
    """The route only calls the engine; engine.py's docstring promises this."""
    route_src = inspect.getsource(main)
    assert "UPDATE quotes SET status = 'cancelled'" not in route_src
    assert "UPDATE messages SET disposition" not in route_src
    assert hasattr(engine, "apply_cancel")


def test_extract_message_does_not_renormalize_or_reinvent_qty_pattern():
    src = inspect.getsource(extract.extract_message)
    assert "_normalize" not in src, "already-normalized text is delegated"
    # no hand-rolled duplicate of _QTY_PATTERNS[1]
    assert "que\\\\s+sean|sean" not in src.replace(" ", "")


def test_intent_is_a_literal():
    hint = extract.MessageExtraction.__annotations__["intent"]
    # Literal[...] arrives as typing.Literal in 3.10+ (or typing_extensions)
    assert get_origin(hint) is Literal or "Literal" in str(hint)
    assert set(get_args(hint)) == {"revise", "create", "question", "cancel", "none"}


def test_dead_field_removed_and_skus_renamed():
    assert not hasattr(extract.ExtractionResult, "__annotations__") or \
        "pending_mentions" not in extract.ExtractionResult.__annotations__
    import app.catalog as catalog
    assert not hasattr(catalog, "SKUS")
    assert hasattr(catalog, "valid_skus")


def test_record_message_receives_the_payload_object():
    """Six travelling params replaced by the MessageIn (data clump fix)."""
    sig = inspect.signature(engine.record_message)
    params = list(sig.parameters)
    assert params[1] == "payload", f"expected payload first, got {params}"
