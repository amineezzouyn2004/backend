from fastapi import APIRouter

from app.config import get_settings
from app.errors import DomainProblem
from app.schemas.catalog import OfferPublic, QuoteRequest, QuoteResponse
from app.services.catalog import (
    OFFERS, DuplicateProductError, OfferUnavailableError,
    ProductOfferUnconfiguredError, UpsellUnavailableError, quote_cart,
)


router = APIRouter(prefix="/v1/offers", tags=["offers"])


@router.get("", response_model=list[OfferPublic])
def list_offers() -> list[OfferPublic]:
    demo = get_settings().demo_offer_mapping_enabled
    return [offer.to_public(demo) for offer in OFFERS.values()]


@router.post("/quote", response_model=QuoteResponse)
def quote(payload: QuoteRequest) -> QuoteResponse:
    settings = get_settings()
    try:
        return quote_cart(
            payload.items,
            demo_enabled=settings.demo_offer_mapping_enabled,
            upsell_intent=payload.upsell_intent,
            upsell_enabled=settings.upsell_enabled,
            upsell_product_slug=settings.upsell_product_slug,
        )
    except OfferUnavailableError as exc:
        raise DomainProblem(409, "OFFER_UNAVAILABLE", "العرض غير متاح", "اختاري عرضًا متاحًا ثم أعيدي المحاولة.") from exc
    except ProductOfferUnconfiguredError as exc:
        raise DomainProblem(409, "PRODUCT_OFFER_UNCONFIGURED", "العرض غير مربوط بالمنتج", "لا يمكن تسعير هذا المنتج قبل اعتماد ربط العرض.") from exc
    except DuplicateProductError as exc:
        raise DomainProblem(422, "DUPLICATE_PRODUCT", "اختيار مكرر", "اختاري عرضًا واحدًا فقط لكل منتج.") from exc
    except UpsellUnavailableError as exc:
        raise DomainProblem(409, "UPSELL_UNAVAILABLE", "الإضافة غير متاحة", "الإضافة الاختيارية غير مهيأة حاليًا.") from exc
