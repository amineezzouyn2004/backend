from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.session import get_db
from app.errors import DomainProblem
from app.models.tracking import TrackingEvent
from app.repositories.orders import OrderRepository
from app.schemas.order import OrderCreate, OrderPublic
from app.services.catalog import (
    DuplicateProductError, OfferUnavailableError,
    ProductOfferUnconfiguredError, UpsellUnavailableError,
)
from app.services.orders import IdempotencyConflict, create_order, to_public
from app.services.phone import InvalidMoroccanPhone


router = APIRouter(prefix="/v1/orders", tags=["orders"])


@router.post("", response_model=OrderPublic, status_code=201)
def create(
    payload: OrderCreate,
    request: Request,
    response: Response,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=200)],
    db: Session = Depends(get_db),
) -> OrderPublic:
    try:
        result = create_order(
            db, payload, idempotency_key, get_settings(),
            user_agent=request.headers.get("user-agent"),
        )
    except InvalidMoroccanPhone as exc:
        raise DomainProblem(422, "PHONE_INVALID", "رقم الهاتف غير صالح", "راجعي رقم الهاتف المغربي وأدخليه من دون نص إضافي.") from exc
    except OfferUnavailableError as exc:
        raise DomainProblem(409, "OFFER_UNAVAILABLE", "العرض غير متاح", "اختاري عرضًا متاحًا ثم أعيدي المحاولة.") from exc
    except ProductOfferUnconfiguredError as exc:
        raise DomainProblem(409, "PRODUCT_OFFER_UNCONFIGURED", "العرض غير مربوط بالمنتج", "هذا الربط متاح في demo المحلي فقط حتى اعتماده.") from exc
    except DuplicateProductError as exc:
        raise DomainProblem(422, "DUPLICATE_PRODUCT", "اختيار مكرر", "اختاري عرضًا واحدًا فقط لكل منتج.") from exc
    except UpsellUnavailableError as exc:
        raise DomainProblem(409, "UPSELL_UNAVAILABLE", "الإضافة غير متاحة", "الإضافة الاختيارية غير مهيأة حاليًا.") from exc
    except IdempotencyConflict as exc:
        raise DomainProblem(409, "IDEMPOTENCY_CONFLICT", "تعارض المحاولة", "استخدمي مفتاح محاولة جديدًا لهذا الطلب المختلف.") from exc
    response.headers["Idempotency-Replayed"] = str(result.replayed).lower()
    response.headers["Cache-Control"] = "no-store"
    return result.response


@router.get("/{public_reference}", response_model=OrderPublic)
def retrieve(public_reference: str, response: Response, db: Session = Depends(get_db)) -> OrderPublic:
    order = OrderRepository(db).find_by_public_reference(public_reference)
    if order is None:
        raise DomainProblem(404, "ORDER_NOT_FOUND", "الطلب غير موجود", "تعذر العثور على مرجع الطلب.")
    event_id = db.scalar(
        select(TrackingEvent.internal_event_id).where(
            TrackingEvent.order_id == order.id,
            TrackingEvent.event_type == "OrderSubmitted",
        )
    )
    if event_id is None:
        raise DomainProblem(500, "INTERNAL_ERROR", "تعذر إكمال الطلب", "تعذر تحميل تأكيد الطلب.")
    response.headers["Cache-Control"] = "no-store, private"
    return to_public(order, event_id)
