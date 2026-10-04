"""Regression tests for optional city validation and sandbox metadata.

City is optional free text. When ALLOWED_CITIES is empty, any reasonable
trimmed city (or null) is accepted and stored in safe_metadata when present.
An allow-list is not required and must not be invented. When the list is
populated, a provided city must match; missing city remains allowed.
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


def test_resolve_city_accepts_optional_free_text_when_allow_list_is_empty() -> None:
    assert resolve_city(None, []) is None
    assert resolve_city("  ", []) is None
    assert resolve_city("Casablanca", []) == "Casablanca"
    assert resolve_city("  الدار البيضاء  ", []) == "الدار البيضاء"
    assert resolve_city("Fès", []) == "Fès"


def test_resolve_city_rejects_unreasonable_values() -> None:
    with pytest.raises(InvalidCity):
        resolve_city("12345", [])
    with pytest.raises(InvalidCity):
        resolve_city("---", [])


def test_resolve_city_optional_even_when_list_present() -> None:
    allowed = ["Casablanca", "Rabat"]
    assert resolve_city(None, allowed) is None
    assert resolve_city("", allowed) is None
    assert resolve_city("Casablanca", allowed) == "Casablanca"
    assert resolve_city("  Rabat  ", allowed) == "Rabat"
    with pytest.raises(InvalidCity):
        resolve_city("Tanger", allowed)


def test_create_order_stores_city_when_no_allow_list(db: Session) -> None:
    result = create_order(db, _payload(city="Casablanca"), "city-key-1", _settings())
    order = db.scalar(
        select(Order).where(Order.public_reference == result.response.public_reference)
    )
    assert order is not None
    history = db.scalars(
        select(OrderStatusHistory).where(OrderStatusHistory.order_id == order.id)
    ).all()
    assert len(history) == 1
    assert (history[0].safe_metadata or {}).get("city") == "Casablanca"


def test_create_order_accepts_missing_city_when_allow_list_present(db: Session) -> None:
    cfg = _settings(allowed_cities="Casablanca,Rabat")
    result = create_order(db, _payload(city=None), "city-key-2", cfg)
    order = db.scalar(
        select(Order).where(Order.public_reference == result.response.public_reference)
    )
    assert order is not None
    entry = db.scalars(
        select(OrderStatusHistory).where(OrderStatusHistory.order_id == order.id)
    ).first()
    assert entry is not None
    assert "city" not in (entry.safe_metadata or {})


def test_create_order_rejects_unsupported_city_when_allow_list_present(
    db: Session,
) -> None:
    cfg = _settings(allowed_cities="Casablanca,Rabat")
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
