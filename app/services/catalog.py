from dataclasses import dataclass
from typing import Literal

from app.schemas.catalog import (
    DevelopmentMedia,
    OfferPublic,
    ProductPublic,
    QuoteItemPublic,
    QuoteResponse,
)


INFORMATION_REQUIRED = "TODO — INFORMATION REQUIRED"


@dataclass(frozen=True)
class CanonicalProduct:
    id: str
    slug: str
    name_ar: str
    related: tuple[str, ...]
    information_required: tuple[str, ...]

    def to_public(self, demo_enabled: bool) -> ProductPublic:
        return ProductPublic(
            id=self.id,
            slug=self.slug,
            name_ar=self.name_ar,
            publish_status="development_blocked",
            media=[
                DevelopmentMedia(
                    kind="development_placeholder",
                    label_ar="صورة مؤقتة — غير للنشر",
                )
            ],
            information_required=list(self.information_required),
            eligible_offer_codes=list(OFFERS) if demo_enabled else [],
            offer_mapping_mode="development_demo" if demo_enabled else "unconfigured",
            related_product_slugs=list(self.related),
        )


PRODUCTS = {
    product.slug: product
    for product in (
        CanonicalProduct(
            "product_smart_baby_nasal_aspirator",
            "smart-baby-nasal-aspirator",
            "شفّاط الأنف الذكي للرضّع",
            ("smart-baby-sleep-lamp", "natural-calming-baby-massage-oil"),
            (f"{INFORMATION_REQUIRED}: facts, safety, usage, media rights",),
        ),
        CanonicalProduct(
            "product_smart_baby_sleep_lamp",
            "smart-baby-sleep-lamp",
            "مصباح النوم الذكي بالصوت والحركة",
            ("smart-baby-nasal-aspirator", "natural-calming-baby-massage-oil"),
            (f"{INFORMATION_REQUIRED}: facts, safety, usage, media rights",),
        ),
        CanonicalProduct(
            "product_natural_calming_baby_massage_oil",
            "natural-calming-baby-massage-oil",
            "زيت مساج طبيعي مهدّئ للأطفال",
            ("smart-baby-sleep-lamp",),
            (f"{INFORMATION_REQUIRED}: ingredients, safety, usage, media rights",),
        ),
    )
}


@dataclass(frozen=True)
class CanonicalOffer:
    code: str
    version: int
    quantity: int
    total_minor: int

    @property
    def reference_total_minor(self) -> int:
        return 39_900 * self.quantity

    @property
    def saving_minor(self) -> int:
        return self.reference_total_minor - self.total_minor

    @property
    def per_unit_minor(self) -> int:
        return (self.total_minor + self.quantity // 2) // self.quantity

    def to_public(self, demo_enabled: bool) -> OfferPublic:
        return OfferPublic(
            code=self.code,
            version=self.version,
            quantity=self.quantity,
            currency="MAD",
            total_minor=self.total_minor,
            reference_total_minor=self.reference_total_minor,
            saving_minor=self.saving_minor,
            per_unit_minor=self.per_unit_minor,
            per_unit_is_approximate=self.total_minor % self.quantity != 0,
            applicability_status=(
                "development_demo" if demo_enabled else "blocked_product_linkage"
            ),
        )


OFFERS = {
    offer.code: offer
    for offer in (
        CanonicalOffer("OFFER_1", 1, 1, 39_900),
        CanonicalOffer("OFFER_2", 1, 2, 69_900),
        CanonicalOffer("OFFER_3", 1, 3, 94_900),
    )
}
UPSELL_CODE = "UPSELL_199"
UPSELL_TOTAL_MINOR = 19_900


class OfferUnavailableError(ValueError):
    pass


class ProductOfferUnconfiguredError(ValueError):
    pass


class DuplicateProductError(ValueError):
    pass


class UpsellUnavailableError(ValueError):
    pass


def get_offer(code: str, requested_version: int | None = None) -> CanonicalOffer:
    offer = OFFERS.get(code)
    if offer is None or (requested_version is not None and requested_version != offer.version):
        raise OfferUnavailableError(code)
    return offer


def quote_cart(
    items: list[object],
    *,
    demo_enabled: bool,
    upsell_intent: bool,
    upsell_enabled: bool,
    upsell_product_slug: str | None,
) -> QuoteResponse:
    seen: set[str] = set()
    quoted: list[QuoteItemPublic] = []
    subtotal = 0
    discount = 0
    for index, item in enumerate(items):
        product_slug = getattr(item, "product_slug")
        if product_slug in seen:
            raise DuplicateProductError(product_slug)
        seen.add(product_slug)
        product = PRODUCTS.get(product_slug)
        if product is None:
            raise ProductOfferUnconfiguredError(product_slug)
        if not demo_enabled:
            raise ProductOfferUnconfiguredError(product_slug)
        offer = get_offer(
            getattr(item, "offer_code"),
            getattr(item, "offer_version"),
        )
        role: Literal["primary", "cross_sell", "upsell"] = (
            "primary" if index == 0 else "cross_sell"
        )
        quoted.append(
            QuoteItemPublic(
                product_id=product.id,
                product_slug=product.slug,
                product_name_ar=product.name_ar,
                offer_code=offer.code,
                offer_version=offer.version,
                offer_quantity=offer.quantity,
                line_total_minor=offer.total_minor,
                saving_minor=offer.saving_minor,
                role=role,
            )
        )
        subtotal += offer.reference_total_minor
        discount += offer.saving_minor

    if upsell_intent:
        if not upsell_enabled or not upsell_product_slug:
            raise UpsellUnavailableError
        product = PRODUCTS.get(upsell_product_slug)
        if product is None or product.slug in seen:
            raise UpsellUnavailableError
        quoted.append(
            QuoteItemPublic(
                product_id=product.id,
                product_slug=product.slug,
                product_name_ar=product.name_ar,
                offer_code=UPSELL_CODE,
                offer_version=1,
                offer_quantity=1,
                line_total_minor=UPSELL_TOTAL_MINOR,
                saving_minor=0,
                role="upsell",
            )
        )
        subtotal += UPSELL_TOTAL_MINOR

    return QuoteResponse(
        items=quoted,
        currency="MAD",
        subtotal_minor=subtotal,
        discount_minor=discount,
        total_minor=subtotal - discount,
        blocker_code="ADDRESS_SHIPPING_TAX_REQUIRED",
    )
