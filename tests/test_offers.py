import pytest

from app.schemas.catalog import QuoteItemRequest
from app.services.catalog import (
    DuplicateProductError, ProductOfferUnconfiguredError, UpsellUnavailableError,
    get_offer, quote_cart,
)


def item(slug: str, offer: str = "OFFER_1") -> QuoteItemRequest:
    return QuoteItemRequest(product_slug=slug, offer_code=offer)


def test_canonical_offer_math_and_rounding() -> None:
    assert get_offer("OFFER_2").saving_minor == 9_900
    assert get_offer("OFFER_2").per_unit_minor == 34_950
    offer = get_offer("OFFER_3")
    assert offer.saving_minor == 24_800
    assert offer.per_unit_minor == 31_633
    assert offer.total_minor == 94_900
    assert offer.per_unit_minor * 3 == 94_899


def test_multi_item_quote_uses_integer_server_totals() -> None:
    quote = quote_cart(
        [
            item("smart-baby-lamp", "OFFER_2"),
            item("jumon-portable-baby-nasal-aspirator", "OFFER_1"),
        ],
        demo_enabled=True,
        upsell_intent=False,
        upsell_enabled=False,
        upsell_product_slug=None,
    )
    assert quote.subtotal_minor == 119_700
    assert quote.discount_minor == 9_900
    assert quote.total_minor == 109_800
    assert quote.shipping_minor is None
    assert quote.total_is_final is False
    assert [line.role for line in quote.items] == ["primary", "cross_sell"]


def test_production_mapping_quotes_without_demo_flag() -> None:
    quote = quote_cart(
        [item("smart-baby-lamp"), item("label-baby-oil", "OFFER_3")],
        demo_enabled=False,
        upsell_intent=False,
        upsell_enabled=False,
        upsell_product_slug=None,
    )
    assert quote.total_minor == 39_900 + 94_900
    assert [line.offer_code for line in quote.items] == ["OFFER_1", "OFFER_3"]


def test_unknown_product_and_duplicates_are_rejected() -> None:
    with pytest.raises(ProductOfferUnconfiguredError):
        quote_cart(
            [item("unknown-product")],
            demo_enabled=False,
            upsell_intent=False,
            upsell_enabled=False,
            upsell_product_slug=None,
        )
    with pytest.raises(DuplicateProductError):
        quote_cart(
            [item("smart-baby-lamp"), item("smart-baby-lamp")],
            demo_enabled=False,
            upsell_intent=False,
            upsell_enabled=False,
            upsell_product_slug=None,
        )


def test_upsell_is_199_and_requires_full_configuration() -> None:
    with pytest.raises(UpsellUnavailableError):
        quote_cart(
            [item("smart-baby-lamp")],
            demo_enabled=True,
            upsell_intent=True,
            upsell_enabled=False,
            upsell_product_slug=None,
        )
    quote = quote_cart(
        [item("smart-baby-lamp")],
        demo_enabled=True,
        upsell_intent=True,
        upsell_enabled=True,
        upsell_product_slug="jumon-portable-baby-nasal-aspirator",
    )
    assert quote.items[-1].role == "upsell"
    assert quote.items[-1].line_total_minor == 19_900
    assert quote.total_minor == 59_800
