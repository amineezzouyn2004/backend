from datetime import datetime, timezone
from uuid import UUID

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.config import Settings
from app.db.base import Base
from app.models.order import (
    AttributionRecord, ConsentRecord, Order, OrderItem, OrderStatusHistory,
)
from app.models.tracking import OutboxEvent, TrackingEvent, WebhookReceipt
from app.schemas.order import OrderCreate
from app.services.orders import IdempotencyConflict, create_order


@pytest.fixture
def db() -> Session:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        yield session


def settings(**overrides: object) -> Settings:
    return Settings(
        database_url="sqlite+pysqlite:///:memory:",
        demo_offer_mapping_enabled=True,
        **overrides,
    )


def payload(name: str = "مريم العلوي") -> OrderCreate:
    return OrderCreate(
        full_name=name,
        phone="0612345678",
        items=[
            {
                "product_slug": "smart-baby-nasal-aspirator",
                "offer_code": "OFFER_3",
            },
            {
                "product_slug": "smart-baby-sleep-lamp",
                "offer_code": "OFFER_1",
            },
        ],
        consent={
            "notice_version": "2026-08-v1",
            "action": "reject",
            "advertising": False,
            "occurred_at": datetime.now(timezone.utc),
            "source": "banner",
        },
        attribution={
            "source": "direct",
            "landing_page": "https://hanin.cc/products",
            "utm_source": "test-source",
            "captured_at": datetime.now(timezone.utc),
        },
    )


def test_order_uses_server_price_and_replays_idempotently(db: Session) -> None:
    request = payload()
    first = create_order(db, request, "fixed-key-123", settings(), user_agent="test-agent")
    replay = create_order(db, request, "fixed-key-123", settings(), user_agent="changed")
    assert first.replayed is False
    assert replay.replayed is True
    assert first.response == replay.response
    assert first.response.total_minor == 134_800
    assert first.response.total_is_final is False
    assert len(first.response.items) == 2
    assert db.scalar(select(func.count(Order.id))) == 1
    assert db.scalar(select(func.count(OrderStatusHistory.id))) == 1
    assert db.scalar(select(func.count(ConsentRecord.id))) == 1
    attribution = db.scalar(select(AttributionRecord))
    assert attribution is not None
    assert attribution.user_agent == "test-agent"


def test_idempotency_conflict_for_different_request(db: Session) -> None:
    create_order(db, payload(), "fixed-key-456", settings())
    with pytest.raises(IdempotencyConflict):
        create_order(db, payload(name="اسم مختلف"), "fixed-key-456", settings())


def test_tracking_and_sheets_outbox_share_event_id_without_ad_delivery(db: Session) -> None:
    result = create_order(
        db,
        payload(),
        "fixed-key-789",
        settings(
            sheets_webhook_enabled=True,
            sheets_webhook_url="https://example.invalid/exec",
            sheets_webhook_secret="test-secret",
        ),
    )
    tracking_id = db.scalar(select(TrackingEvent.internal_event_id))
    outbox = db.scalar(select(OutboxEvent))
    assert isinstance(result.response.event_id, UUID)
    assert outbox is not None
    assert result.response.event_id == tracking_id == outbox.internal_event_id
    assert outbox.destination == "sheets"
    assert outbox.payload["full_name"] == "مريم العلوي"


def test_database_constraints_and_webhook_dedup(db: Session) -> None:
    created = create_order(db, payload(), "fixed-key-constraints", settings())
    order = db.scalar(select(Order).where(Order.public_reference == created.response.public_reference))
    assert order is not None
    db.add(
        OrderItem(
            order_id=order.id,
            name_snapshot_ar="invalid",
            offer_quantity=0,
            quantity=1,
            unit_minor=1,
            line_total_minor=1,
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
    db.add(WebhookReceipt(provider="carrier", external_event_id="same", signature_version="v1"))
    db.commit()
    db.add(WebhookReceipt(provider="carrier", external_event_id="same", signature_version="v1"))
    with pytest.raises(IntegrityError):
        db.commit()
