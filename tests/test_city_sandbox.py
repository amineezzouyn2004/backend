"""Regression tests for optional city validation and sandbox metadata.

These cover STEP 1 (F) of the production-readiness audit:
- When ALLOWED_CITIES is empty the city field is accepted but silently dropped
  server-side (no schema change, no invented coverage).
- When ALLOWED_CITIES is populated, city becomes required and validated.
- When SANDBOX_MODE=true, the initial status_history entry is tagged so QA
  runs against a shared DB can be filtered out without touching the schema.
"""

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.config import Settings
from app.db.base import Base
from app.models.order import Order, OrderStatusHistory
from app.schemas.order import OrderCreate
from app.services.orders import (
    InvalidCity,
    create_order,
    resolve_city,
)


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


def _settings(**overrides: object) -> Settings:
    return Settings(
        database_url="sqlite+pysqlite:///:memory:",
        demo_offer_mapping_enabled=True,
        **overrides,
    )


def _payload(city: str | None = None) -> OrderCreate:
    return OrderCreate(
        full_name="مريم العلوي",
        phone="0612345678",
        city=city,
        items=[
            {
                "product_slug": "smart-baby-nasal-aspirator",
                "offer_code": "OFFER_1",
            }
        ],
        consent={
            "notice_version": "2026-08-v1",
            "action": "reject",
            "advertising": False,
            "occurred_at": datetime.now(timezone.utc),
            "source": "banner",
        },
    )


def test_resolve_city_returns_none_when_allow_list_is_empty() -> None:
    assert resolve_city(None, []) is None
    assert resolve_city("Casablanca", []) is None
    assert resolve_city("  ", []) is None


def test_resolve_city_requires_and_validates_when_list_present() -> None:
    allowed = ["Casablanca", "Rabat"]
    assert resolve_city("Casablanca", allowed) == "Casablanca"
    assert resolve_city("  Rabat  ", allowed) == "Rabat"
    with pytest.raises(InvalidCity):
        resolve_city(None, allowed)
    with pytest.raises(InvalidCity):
        resolve_city("", allowed)
    with pytest.raises(InvalidCity):
        resolve_city("Tanger", allowed)


def test_create_order_ignores_city_when_no_allow_list(db: Session) -> None:
    result = create_order(db, _payload(city="Casablanca"), "city-key-1", _settings())
    order = db.scalar(
        select(Order).where(Order.public_reference == result.response.public_reference)
    )
    assert order is not None
    history = db.scalars(
        select(OrderStatusHistory).where(OrderStatusHistory.order_id == order.id)
    ).all()
    assert len(history) == 1
    # City is silently dropped; no `city` key in safe_metadata.
    assert "city" not in (history[0].safe_metadata or {})


def test_create_order_rejects_unsupported_city_when_allow_list_present(
    db: Session,
) -> None:
    cfg = _settings(allowed_cities="Casablanca,Rabat")
    with pytest.raises(InvalidCity):
        create_order(db, _payload(city=None), "city-key-2", cfg)
    with pytest.raises(InvalidCity):
        create_order(db, _payload(city="Tanger"), "city-key-3", cfg)


def test_create_order_records_city_and_sandbox_flag_in_status_history(
    db: Session,
) -> None:
    cfg = _settings(allowed_cities="Casablanca,Rabat", sandbox_mode=True)
    result = create_order(db, _payload(city="Casablanca"), "city-key-4", cfg)
    order = db.scalar(
        select(Order).where(Order.public_reference == result.response.public_reference)
    )
    assert order is not None
    entry = db.scalars(
        select(OrderStatusHistory).where(OrderStatusHistory.order_id == order.id)
    ).first()
    assert entry is not None
    assert entry.safe_metadata.get("city") == "Casablanca"
    assert entry.safe_metadata.get("sandbox") is True
