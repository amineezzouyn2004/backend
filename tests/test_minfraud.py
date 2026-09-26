from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import UUID

import pytest
from minfraud.errors import HTTPError
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.config import Settings
from app.db.base import Base
from app.integrations.minfraud import (
    MinFraudGateway,
    build_report,
    build_transaction,
    client_ip_for_minfraud,
    is_minfraud_ready,
)
from app.integrations.minfraud.ip import is_public_ip
from app.models.minfraud import MinFraudAssessment
from app.models.order import Order, OrderStatus
from app.models.tracking import DeliveryStatus, OutboxEvent
from app.schemas.order import OrderCreate
from app.services.orders import create_order
from app.worker import process_outbox


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


def ready_settings(**overrides: object) -> Settings:
    return settings(
        maxmind_minfraud_enabled=True,
        maxmind_account_id="12345",
        maxmind_license_key="test-license-key",
        **overrides,
    )


class FakeScore:
    def __init__(self) -> None:
        self.id = "5bc5d6c2-b2c8-40af-87f4-6d61af86b6ae"
        self.risk_score = 12.5
        self.disposition = SimpleNamespace(
            action="accept", reason="default", rule_label=None
        )
        self.ip_address = SimpleNamespace(risk=1.2)
        self.warnings = [SimpleNamespace(code="IP_ADDRESS_RESERVED")]
        self.risk_score_reasons = []


class FakeClient:
    def __init__(self) -> None:
        self.score_calls: list[dict] = []
        self.report_calls: list[dict] = []

    def score(self, transaction: dict) -> FakeScore:
        self.score_calls.append(transaction)
        return FakeScore()

    def insights(self, transaction: dict) -> FakeScore:
        return self.score(transaction)

    def factors(self, transaction: dict) -> FakeScore:
        return self.score(transaction)

    def report(self, document: dict) -> None:
        self.report_calls.append(document)


class TimeoutClient:
    def score(self, transaction: dict) -> FakeScore:
        raise HTTPError("unavailable", 503, "https://minfraud.maxmind.com/minfraud/v2.0/score")

    def report(self, document: dict) -> None:
        raise HTTPError("unavailable", 503, "https://minfraud.maxmind.com/minfraud/v2.0/transactions/report")


def test_disabled_by_default_enqueues_no_minfraud_and_makes_no_http(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*args: object, **kwargs: object) -> None:
        raise AssertionError("minfraud client must not be constructed")

    monkeypatch.setattr("app.integrations.minfraud.gateway.Client", boom)
    result = create_order(db, payload(), "minfraud-off-key", settings())
    assert result.replayed is False
    assert db.scalar(
        select(func.count(OutboxEvent.id)).where(OutboxEvent.destination == "minfraud")
    ) == 0
    assert db.scalar(select(func.count(MinFraudAssessment.id))) == 0


def test_enabled_without_credentials_is_noop(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*args: object, **kwargs: object) -> None:
        raise AssertionError("minfraud client must not be constructed")

    monkeypatch.setattr("app.integrations.minfraud.gateway.Client", boom)
    cfg = settings(maxmind_minfraud_enabled=True)
    assert is_minfraud_ready(cfg) is False
    create_order(db, payload(), "minfraud-nocreds-key", cfg)
    assert db.scalar(
        select(func.count(OutboxEvent.id)).where(OutboxEvent.destination == "minfraud")
    ) == 0


def test_payload_uses_collected_fields_only() -> None:
    transaction = build_transaction(
        {
            "order_public_reference": "ref-abc",
            "full_name": "مريم العلوي",
            "phone_e164": "+212612345678",
            "subtotal_minor": 134_800,
            "discount_minor": 24_800,
            "total_minor": 110_000,
            "currency": "MAD",
            "offer_code": "OFFER_3",
            "created_at": "2026-08-26T09:00:00+00:00",
            "client_ip": "8.8.8.8",
            "user_agent": "HaninTest/1.0",
            "accept_language": "ar",
            "items": [
                {"item_id": "smart-baby-nasal-aspirator", "quantity": 1, "unit_minor": 39_900}
            ],
        }
    )
    assert "email" not in transaction
    assert "credit_card" not in transaction
    assert "payment" not in transaction
    assert "address" not in transaction.get("billing", {})
    assert "city" not in transaction.get("shipping", {})
    assert transaction["event"]["transaction_id"] == "ref-abc"
    assert transaction["event"]["type"] == "purchase"
    assert transaction["order"]["amount"] == 1348.0
    assert transaction["order"]["currency"] == "MAD"
    assert transaction["device"]["ip_address"] == "8.8.8.8"
    assert transaction["device"]["user_agent"] == "HaninTest/1.0"
    assert transaction["billing"]["phone_country_code"] == "212"
    assert transaction["billing"]["phone_number"] == "612345678"
    assert transaction["billing"]["first_name"] == "مريم"
    assert transaction["billing"]["last_name"] == "العلوي"
    assert transaction["shopping_cart"][0]["price"] == 399.0


def test_order_creation_enqueues_minfraud_without_calling_network(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*args: object, **kwargs: object) -> None:
        raise AssertionError("minfraud HTTP must not run in create_order")

    monkeypatch.setattr("app.integrations.minfraud.gateway.Client", boom)
    result = create_order(
        db,
        payload(),
        "minfraud-enqueue-key",
        ready_settings(),
        user_agent="Mozilla/5.0 test",
        client_ip="8.8.8.8",
        accept_language="ar",
    )
    order = db.scalar(select(Order).where(Order.public_reference == result.response.public_reference))
    assert order is not None
    assert order.status is OrderStatus.PENDING
    outbox = db.scalar(select(OutboxEvent).where(OutboxEvent.destination == "minfraud"))
    assert outbox is not None
    assert outbox.payload["phone_e164"] == "+212612345678"
    assert outbox.payload["client_ip"] == "8.8.8.8"
    assert outbox.payload["currency"] == "MAD"
    assert "email" not in outbox.payload
    transaction = build_transaction(outbox.payload)
    assert transaction["order"]["amount"] == order.subtotal_minor / 100
    assert db.scalar(select(func.count(MinFraudAssessment.id))) == 0


def test_worker_persists_score_without_changing_order_status(db: Session) -> None:
    created = create_order(db, payload(), "minfraud-persist-key", ready_settings())
    order = db.scalar(select(Order).where(Order.public_reference == created.response.public_reference))
    assert order is not None
    fake = FakeClient()
    gateway = MinFraudGateway(12345, "test-license-key", client=fake)
    processed = process_outbox(db, ready_settings(), minfraud_gateway=gateway)
    assert processed == 1
    assert fake.score_calls
    assessment = db.scalar(select(MinFraudAssessment))
    assert assessment is not None
    assert str(assessment.minfraud_id) == "5bc5d6c2-b2c8-40af-87f4-6d61af86b6ae"
    assert float(assessment.risk_score) == 12.5
    assert assessment.disposition_action == "accept"
    assert assessment.warning_codes == ["IP_ADDRESS_RESERVED"]
    assert order.status is OrderStatus.PENDING
    outbox = db.scalar(select(OutboxEvent).where(OutboxEvent.destination == "minfraud"))
    assert outbox is not None
    assert outbox.status is DeliveryStatus.SENT


def test_minfraud_timeout_does_not_fail_order_or_cancel_it(db: Session) -> None:
    created = create_order(db, payload(), "minfraud-timeout-key", ready_settings())
    order = db.scalar(select(Order).where(Order.public_reference == created.response.public_reference))
    assert order is not None
    gateway = MinFraudGateway(12345, "test-license-key", client=TimeoutClient())
    processed = process_outbox(db, ready_settings(), minfraud_gateway=gateway)
    assert processed == 1
    db.refresh(order)
    assert order.status is OrderStatus.PENDING
    assert created.response.status is OrderStatus.PENDING
    outbox = db.scalar(select(OutboxEvent).where(OutboxEvent.destination == "minfraud"))
    assert outbox is not None
    assert outbox.status is DeliveryStatus.FAILED
    assert outbox.last_error_code == "http_503"
    assert db.scalar(select(func.count(MinFraudAssessment.id))) == 0


def test_xff_ignored_without_trusted_proxy() -> None:
    request = SimpleNamespace(
        client=SimpleNamespace(host="127.0.0.1"),
        headers={"x-forwarded-for": "8.8.8.8"},
    )
    assert client_ip_for_minfraud(request, []) is None
    trusted = SimpleNamespace(
        client=SimpleNamespace(host="10.0.0.2"),
        headers={"x-forwarded-for": "8.8.8.8"},
    )
    assert client_ip_for_minfraud(trusted, ["10.0.0.2"]) == "8.8.8.8"
    assert is_public_ip("127.0.0.1") is False
    assert is_public_ip("8.8.8.8") is True


def test_report_transaction_hook_uses_official_tags() -> None:
    fake = FakeClient()
    gateway = MinFraudGateway(12345, "test-license-key", client=fake)
    ok = gateway.report_transaction(
        tag="suspected_fraud",
        minfraud_id="5bc5d6c2-b2c8-40af-87f4-6d61af86b6ae",
        transaction_id="ref-abc",
    )
    assert ok.delivered is True
    assert fake.report_calls[0]["tag"] == "suspected_fraud"
    rejected = gateway.report_transaction(tag="cod_return")
    assert rejected.delivered is False
    assert rejected.error_code == "invalid_minfraud_report_tag"
    document = build_report(
        tag="chargeback",
        minfraud_id="5bc5d6c2-b2c8-40af-87f4-6d61af86b6ae",
    )
    assert document["tag"] == "chargeback"


def test_is_minfraud_ready_requires_flag_and_credentials() -> None:
    assert is_minfraud_ready(settings()) is False
    assert is_minfraud_ready(settings(maxmind_minfraud_enabled=True)) is False
    assert is_minfraud_ready(ready_settings()) is True
    assert isinstance(UUID("5bc5d6c2-b2c8-40af-87f4-6d61af86b6ae"), UUID)
