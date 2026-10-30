"""Pydantic models: the API boundary where a foreign SKU is impossible.

LineItem.sku is validated against the catalog at parse time — an LLM adapter
placed behind this boundary could not hallucinate a SKU into storage even if
it tried; the request would 422 before reaching the engine.
"""
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from .catalog import SKUS


class LineItem(BaseModel):
    sku: str
    qty: int = Field(gt=0)

    @field_validator("sku")
    @classmethod
    def sku_must_be_in_catalog(cls, v: str) -> str:
        if v not in SKUS():
            raise ValueError(f"SKU {v!r} is not in the catalog")
        return v


class QuoteOut(BaseModel):
    quote_id: str
    status: str
    conversations: list[str]
    line_items: list[LineItem]


class QuotesOut(BaseModel):
    quotes: list[QuoteOut]


class HistoryMessage(BaseModel):
    direction: Literal["inbound", "outbound"]
    timestamp: str
    text: str


class ConversationIn(BaseModel):
    customer_id: str
    conversation_id: str
    customer_name: str | None = None
    conversation_history: list[HistoryMessage]


class MessageIn(BaseModel):
    message_id: str
    conversation_id: str
    customer_id: str
    direction: Literal["inbound", "outbound"]
    timestamp: str
    text: str


class ReviewResolveIn(BaseModel):
    decision: Literal["apply", "discard"]
    quote_id: str | None = None
    # required, not defaulted: the audit must always be able to answer
    # "who/what decided" (ticket 11)
    resolved_by: str = Field(min_length=1)
