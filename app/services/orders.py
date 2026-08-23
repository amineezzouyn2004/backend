import hashlib
import json
import secrets
import unicodedata
import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.config import Settings
from app.models.order import (
    AttributionRecord, ConsentRecord, IdempotencyRecord, Order, OrderItem,
    OrderStatus, OrderStatusHistory,
)
from app.models.tracking import OutboxEvent, TrackingEvent
from app.repositories.orders import OrderRepository
from app.schemas.order import OrderCreate, OrderPublic, OrderStatusEntryPublic
from app.services.catalog import quote_cart
from app.services.phone import normalize_moroccan_mobile


class IdempotencyConflict(ValueError):
    pass


def normalize_name(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).split())


def request_fingerprint(payload: OrderCreate, normalized_name: str, phone: str) -> str:
    canonical = payload.model_dump(mode="json")
    canonical["full_name"] = normalized_name
    canonical["phone"] = phone
    canonical.pop("client_event_id", None)
    return hashlib.sha256(
        json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


def to_public(order: Order, event_id: uuid.UUID) -> OrderPublic:
    return OrderPublic(
        public_reference=order.public_reference,
        status=order.status,
        items=[
            {
                "product_id": item.sku_snapshot or item.product_slug or "unconfigured",
                "product_slug": item.product_slug or "unconfigured",
                "product_name_ar": item.name_snapshot_ar,
                "offer_code": item.offer_code or order.offer_code,
                "offer_version": item.offer_version or order.offer_version,
                "offer_quantity": item.offer_quantity,
                "line_total_minor": item.line_total_minor,
                "saving_minor": item.saving_minor,
                "role": item.role,
            }
            for item in order.items
        ],
        currency="MAD",
        subtotal_minor=order.subtotal_minor,
        discount_minor=order.discount_minor,
        total_minor=order.total_minor,
        event_id=event_id,
        status_history=[
            OrderStatusEntryPublic(status=entry.to_status, occurred_at=entry.occurred_at)
            for entry in order.status_history
        ],
        blocker_code="ADDRESS_SHIPPING_TAX_REQUIRED",
        message_ar=(
            "استلمنا الطلب بحالة معلّقة للمراجعة التشغيلية. لا يُعد الطلب "
            "مؤكدًا للشحن، لأن العنوان والشحن والضرائب وطريقة الإكمال غير محسومة."
        ),
    )


@dataclass(frozen=True)
class CreateOrderResult:
    response: OrderPublic
    replayed: bool


def create_order(
    db: Session,
    payload: OrderCreate,
    idempotency_key: str,
    settings: Settings,
    *,
    user_agent: str | None = None,
) -> CreateOrderResult:
    name = normalize_name(payload.full_name)
    phone = normalize_moroccan_mobile(payload.phone)
    fingerprint = request_fingerprint(payload, name, phone)
    repository = OrderRepository(db)
    existing = repository.find_idempotency("create_order", idempotency_key)
    if existing:
        if existing.request_fingerprint != fingerprint:
            raise IdempotencyConflict
        return CreateOrderResult(
            response=OrderPublic.model_validate(existing.response_json),
            replayed=True,
        )

    quote = quote_cart(
        payload.items,
        demo_enabled=settings.demo_offer_mapping_enabled,
        upsell_intent=payload.upsell_intent,
        upsell_enabled=settings.upsell_enabled,
        upsell_product_slug=settings.upsell_product_slug,
    )
    consent_id = None
    if payload.consent:
        consent = ConsentRecord(**payload.consent.model_dump())
        db.add(consent)
        db.flush()
        consent_id = consent.id
    attribution_id = None
    if payload.attribution:
        attribution = AttributionRecord(
            **payload.attribution.model_dump(),
            user_agent=(user_agent or "")[:500] or None,
        )
        db.add(attribution)
        db.flush()
        attribution_id = attribution.id

    event_id = payload.client_event_id or uuid.uuid4()
    order = Order(
        public_reference=secrets.token_urlsafe(24),
        status=OrderStatus.PENDING,
        full_name=name,
        phone_e164=phone,
        subtotal_minor=quote.subtotal_minor,
        discount_minor=quote.discount_minor,
        total_minor=quote.total_minor,
        total_is_final=False,
        offer_code=quote.items[0].offer_code,
        offer_version=quote.items[0].offer_version,
        upsell_selected=payload.upsell_intent,
        consent_snapshot_id=consent_id,
        attribution_id=attribution_id,
        utm_source=payload.attribution.utm_source if payload.attribution else None,
        utm_medium=payload.attribution.utm_medium if payload.attribution else None,
        utm_campaign=payload.attribution.utm_campaign if payload.attribution else None,
    )
    for item in quote.items:
        order.items.append(
            OrderItem(
                product_slug=item.product_slug,
                sku_snapshot=item.product_id,
                name_snapshot_ar=item.product_name_ar,
                offer_code=item.offer_code,
                offer_version=item.offer_version,
                offer_quantity=item.offer_quantity,
                role=item.role,
                quantity=1,
                unit_minor=item.line_total_minor,
                line_total_minor=item.line_total_minor,
                saving_minor=item.saving_minor,
            )
        )
    order.status_history.append(
        OrderStatusHistory(
            from_status=None,
            to_status=OrderStatus.PENDING,
            reason_code="order_submitted",
            actor_type="customer",
            safe_metadata={},
        )
    )
    db.add(order)
    db.flush()
    event = TrackingEvent(
        internal_event_id=event_id,
        event_type="OrderSubmitted",
        order_id=order.id,
        source="server",
        payload_version=2,
        consent_snapshot_id=consent_id,
    )
    db.add(event)
    db.flush()

    destinations: list[str] = []
    if settings.sheets_webhook_enabled:
        destinations.append("sheets")
    if settings.tracking_enabled and payload.consent and payload.consent.advertising:
        if settings.meta_capi_enabled:
            destinations.append("meta")
        if settings.tiktok_capi_enabled:
            destinations.append("tiktok")
        if settings.snap_capi_enabled:
            destinations.append("snap")
    for destination in destinations:
        payload_data: dict[str, object] = {
            "schema_version": 2,
            "event_id": str(event_id),
            "event_type": "OrderSubmitted",
            "order_public_reference": order.public_reference,
            "order_status": order.status.value,
            "created_at": order.created_at.isoformat() if order.created_at else None,
            "offer_codes": [item.offer_code for item in quote.items],
            "item_quantities": [item.offer_quantity for item in quote.items],
            "subtotal_minor": order.subtotal_minor,
            "discount_minor": order.discount_minor,
            "shipping_minor": None,
            "tax_minor": None,
            "total_minor": order.total_minor,
            "total_is_final": False,
            "currency": "MAD",
            "consent_version": payload.consent.notice_version if payload.consent else None,
            "utm_source": payload.attribution.utm_source if payload.attribution else None,
            "utm_medium": payload.attribution.utm_medium if payload.attribution else None,
            "utm_campaign": payload.attribution.utm_campaign if payload.attribution else None,
        }
        if destination == "sheets":
            payload_data["full_name"] = name
            payload_data["phone_e164"] = phone
        db.add(
            OutboxEvent(
                internal_event_id=event_id,
                aggregate_type="order",
                aggregate_id=order.id,
                event_type="OrderSubmitted",
                destination=destination,
                payload_version=2,
                payload=payload_data,
            )
        )
    db.flush()
    response = to_public(order, event_id)
    db.add(
        IdempotencyRecord(
            scope="create_order",
            key=idempotency_key,
            request_fingerprint=fingerprint,
            order_id=order.id,
            response_json=response.model_dump(mode="json"),
        )
    )
    db.commit()
    return CreateOrderResult(response=response, replayed=False)
