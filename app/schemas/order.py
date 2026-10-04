from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.order import OrderStatus
from app.schemas.catalog import QuoteItemPublic, QuoteItemRequest


class AttributionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str | None = Field(default=None, max_length=80)
    landing_page: str | None = Field(default=None, max_length=500)
    utm_source: str | None = Field(default=None, max_length=100)
    utm_medium: str | None = Field(default=None, max_length=100)
    utm_campaign: str | None = Field(default=None, max_length=100)
    utm_term: str | None = Field(default=None, max_length=100)
    utm_content: str | None = Field(default=None, max_length=100)
    fbclid: str | None = Field(default=None, max_length=300)
    fbc: str | None = Field(default=None, max_length=300)
    fbp: str | None = Field(default=None, max_length=300)
    ttclid: str | None = Field(default=None, max_length=300)
    ttp: str | None = Field(default=None, max_length=300)
    snap_click_id: str | None = Field(default=None, max_length=300)
    captured_at: datetime | None = None

    @field_validator("*", mode="before")
    @classmethod
    def strip_strings(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class ConsentInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    notice_version: str = Field(min_length=1, max_length=40)
    action: Literal["accept", "reject", "customize", "withdraw"]
    advertising: bool
    occurred_at: datetime
    source: Literal["banner", "preferences", "checkout"]


class OrderCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    full_name: str = Field(min_length=2, max_length=120)
    phone: str = Field(min_length=8, max_length=32)
    # Optional free-text city. Service layer accepts null/empty or a reasonable
    # trimmed name. An allow-list is not required; when empty, the value is
    # stored in status_history.safe_metadata. When populated, a provided city
    # must match. Do not invent cities.
    city: str | None = Field(default=None, max_length=80)
    items: list[QuoteItemRequest] = Field(min_length=1, max_length=10)
    upsell_intent: bool = False
    client_event_id: UUID | None = None
    consent: ConsentInput | None = None
    attribution: AttributionInput | None = None


class OrderStatusEntryPublic(BaseModel):
    status: OrderStatus
    occurred_at: datetime


class OrderPublic(BaseModel):
    public_reference: str
    status: OrderStatus
    items: list[QuoteItemPublic]
    currency: Literal["MAD"]
    subtotal_minor: int
    discount_minor: int
    shipping_minor: None = None
    tax_minor: None = None
    total_minor: int
    total_is_final: Literal[False] = False
    event_id: UUID
    status_history: list[OrderStatusEntryPublic]
    blocker_code: Literal["ADDRESS_SHIPPING_TAX_REQUIRED"]
    message_ar: str
