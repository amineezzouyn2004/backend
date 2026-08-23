from typing import Literal

InternalEvent = Literal[
    "PageViewed", "ProductViewed", "CartItemAdded", "CheckoutStarted",
    "OfferSelected", "UpsellShown", "UpsellAccepted", "UpsellDeclined",
    "OrderSubmitted",
]

MAPPINGS = {
    "PageViewed": {"meta": "PageView", "tiktok": "PageView", "snap": "PAGE_VIEW"},
    "ProductViewed": {"meta": "ViewContent", "tiktok": "ViewContent", "snap": "VIEW_CONTENT"},
    "CartItemAdded": {"meta": "AddToCart", "tiktok": "AddToCart", "snap": "ADD_CART"},
    "CheckoutStarted": {"meta": "InitiateCheckout", "tiktok": "InitiateCheckout", "snap": "START_CHECKOUT"},
}


def map_event(event: str, platform: str) -> str | None:
    # Purchase deliberately has no mapping until COD semantics are approved.
    return MAPPINGS.get(event, {}).get(platform)
