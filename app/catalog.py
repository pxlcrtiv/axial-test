"""Catalog: the single source of SKU truth.

Nothing in the system may name a SKU that isn't in this table. Pydantic models
validate against SKUs(); the extractor can only emit SKUs it matched here.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Sku:
    sku: str
    description: str
    family: str          # coarse product family used by the extractor
    keywords: tuple[str, ...]  # colloquial mentions that map to this SKU
    widths: tuple[str, ...]    # distinguishing widths, e.g. ("1.37",)


CATALOG: dict[str, Sku] = {
    s.sku: s
    for s in [
        Sku("ALFBTC-013-320100", "Lona Frontlit BTE 13 3.20x100", "lona",
            ("lona", "frontlit", "bte"), ("3.20",)),
        Sku("ALMCLC-0909-320100", "Lona Mesh CLN 9x9 3.20x100", "mesh",
            ("mesh", "cln"), ("3.20",)),
        Sku("AVMICS-1A-137050", "Vinil Adhesivo Microperforado 1.37x50", "microperforado",
            ("microperforado", "vinil", "micro"), ("1.37",)),
        Sku("ARACBL-03-122244", "Acrilico Blanco 3mm 1.22x2.44", "acrilico",
            ("acrilico", "acrílico"), ("1.22",)),
    ]
}


def SKUS() -> frozenset[str]:
    return frozenset(CATALOG)
