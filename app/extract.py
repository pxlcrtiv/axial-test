"""Deterministic Spanish extractor — Phase 1.

This is the seam where an LLM adapter would slot in: given conversation
messages, produce structured line items. Today it is pure rules — no tokens
burned, no hallucinated SKUs possible (it can only emit SKUs it matched in
the catalog; an unmatched mention yields nothing).

Approach: messages are split into clauses; each clause carries at most one
(product mention, quantity) pair. Details scattered across messages join
through a *pending mentions* queue maintained for the whole conversation:

  - a clause with a mention but no quantity enqueues a pending mention
    ("...microperforado de 1.37 y 1.50")
  - a clause with a quantity but no mention attaches to the most recent
    pending mention ("Necesitamos 5 rollos")
  - an outbound clause with a width but no mention resolves a pending
    mention's width ("De momento sería de 1.37x50")

The customer's 1.50 m ask resolves to no SKU: the catalog carries only
1.37 for that family, so it can never enter the output.
"""
import re
import unicodedata
from dataclasses import dataclass, field

from .catalog import CATALOG

_NUMBERS = {
    "un": 1, "una": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5,
    "seis": 6, "siete": 7, "ocho": 8, "nueve": 9, "diez": 10,
    "quince": 15, "veinte": 20,
}

_QTY_PATTERNS = [
    # "20 rollos", "5 rollos de", "2 acrilicos blancos"
    re.compile(r"\b(\d+)\s+(?:de\s+|del\s+)?(?:rollos?|piezas?|unidades|uds?|acrilicos?|lonas?)\b"),
    # "que sean 15", "mejor que sean 15"
    re.compile(r"\b(?:que\s+sean|sean)\s+(\d+)\b"),
    # word-number + unit
    re.compile(r"\b(" + "|".join(_NUMBERS) + r")\s+(?:rollos?|piezas?|unidades)\b"),
]

# family detection on normalized text
_FAMILIES: dict[str, re.Pattern] = {
    "lona": re.compile(r"\bfrontlit\b|\blona\s+(?!mesh)"),
    "mesh": re.compile(r"\bmesh\b"),
    "microperforado": re.compile(r"\bmicroperforado\b|\bvinil\b|\bmicro\b"),
    "acrilico": re.compile(r"\bacrilicos?\b"),
}

_WIDTH_AFTER_MENTION = re.compile(r"(\d+[.,]\d+)\s*[x×]\s*\d+")   # 3.20 x 100
_ANY_WIDTH = re.compile(r"(\d+[.,]\d+)")
_NO_CORRECTION = re.compile(r"\bno\s+\d+\b")                      # "15, no 20"


@dataclass
class Mention:
    family: str
    sku: str | None
    width: str | None
    qty: int | None


@dataclass
class ExtractionResult:
    line_items: list[dict] = field(default_factory=list)
    pending_mentions: list[Mention] = field(default_factory=list)


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in text if not unicodedata.combining(c))


def _extract_qty(clause: str) -> int | None:
    for pat in _QTY_PATTERNS:
        m = pat.search(clause)
        if m:
            raw = m.group(1)
            return int(raw) if raw.isdigit() else _NUMBERS[raw]
    return None


def _match_sku(family: str, width: str | None) -> str | None:
    """Catalog match — the ONLY path from text to a SKU. None when the
    mention can't be pinned to exactly one catalog entry (width 1.50)."""
    candidates = [s for s in CATALOG.values() if s.family == family]
    if width is not None:
        exact = [s for s in candidates if width in s.widths]
        if len(exact) == 1:
            return exact[0].sku
        if not exact:
            return None
    return candidates[0].sku if len(candidates) == 1 else None


def _find_mention(clause: str) -> Mention | None:
    for fam, pat in _FAMILIES.items():
        m = pat.search(clause)
        if m:
            wm = _WIDTH_AFTER_MENTION.search(clause, m.end())
            width = wm.group(1).replace(",", ".") if wm else None
            return Mention(family=fam, sku=_match_sku(fam, width), width=width, qty=None)
    return None


def _split_clauses(text: str) -> list[str]:
    return [c.strip() for c in re.split(r"[.,;]|\by\s+(?=si|tambien|aparte|cotizame)", text) if c.strip()]


def extract_conversation(messages: list[dict]) -> ExtractionResult:
    result = ExtractionResult()
    pending: list[Mention] = []

    for msg in messages:
        text = _normalize(msg["text"])
        text = _NO_CORRECTION.sub("", text)  # "15, no 20" -> keeps 15

        for clause in _split_clauses(text):
            mention = _find_mention(clause)
            qty = _extract_qty(clause)

            if mention and qty:
                mention.qty = qty
                if mention.sku:
                    result.line_items.append({"sku": mention.sku, "qty": qty})
                else:
                    pending.append(mention)
            elif mention:
                pending.append(mention)
            elif qty is not None:
                for m in reversed(pending):
                    if m.qty is None:
                        m.qty = qty
                        if m.sku:
                            result.line_items.append({"sku": m.sku, "qty": qty})
                        break
            else:
                # outbound width clarification: "de momento sería de 1.37x50"
                wm = _WIDTH_AFTER_MENTION.search(clause)
                if wm and msg["direction"] == "outbound":
                    for m in reversed(pending):
                        if m.qty is None:
                            w = wm.group(1).replace(",", ".")
                            m.width = w
                            m.sku = _match_sku(m.family, w)
                            if m.qty:  # qty may have arrived before width
                                result.line_items.append({"sku": m.sku, "qty": m.qty})
                            break

    result.pending_mentions = pending
    return result
