from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class DevelopmentMedia(BaseModel):
    kind: Literal["development_placeholder"]
    label_ar: str
    production_eligible: Literal[False] = False


class ProductPublic(BaseModel):
    id: str
    slug: str
    sku: str
    name_ar: str
    publish_status: Literal["development_blocked"]
    media: list[DevelopmentMedia]
    information_required: list[str]
    eligible_offer_codes: list[str]
    offer_mapping_mode: Literal["unconfigured", "development_demo"]
    related_product_slugs: list[str]


class OfferPublic(BaseModel):
    code: str
    version: int
    quantity: int
    currency: Literal["MAD"]
    total_minor: int
    reference_total_minor: int
    saving_minor: int
    per_unit_minor: int
    per_unit_is_approximate: bool
    applicability_status: Literal["blocked_product_linkage", "development_demo"]


class QuoteItemRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_slug: str = Field(min_length=1, max_length=160)
    offer_code: str = Field(min_length=1, max_length=32)
    offer_version: int | None = Field(default=None, ge=1)


class QuoteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[QuoteItemRequest] = Field(min_length=1, max_length=10)
    upsell_intent: bool = False


class QuoteItemPublic(BaseModel):
    product_id: str
    product_slug: str
    sku: str
    product_name_ar: str
    offer_code: str
    offer_version: int
    offer_quantity: int
    line_total_minor: int
    saving_minor: int
    role: Literal["primary", "cross_sell", "upsell"]


class QuoteResponse(BaseModel):
    items: list[QuoteItemPublic]
    currency: Literal["MAD"]
    subtotal_minor: int
    discount_minor: int
    shipping_minor: None = None
    tax_minor: None = None
    total_minor: int
    total_is_final: Literal[False] = False
    blocker_code: Literal["ADDRESS_SHIPPING_TAX_REQUIRED"]
