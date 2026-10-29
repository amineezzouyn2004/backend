from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.config import Settings, get_settings
from app.db.base import Base
from app.db.session import get_db
from app.integrations.geoip.lookup import (
    IpClassification,
    classify_ip,
    is_accepted_morocco,
)
from app.main import app
from app.models.analytics import AnalyticsEvent
from app.models.order import OrderStatus
from app.schemas.order import OrderCreate
from app.services.orders import create_order


@pytest.fixture
def db_engine():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return engine


@pytest.fixture
def client(db_engine):
    def _override_db():
        with Session(db_engine, expire_on_commit=False) as session:
            yield session

    previous = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = _override_db
    with TestClient(app) as test_client:
        yield test_client
    if previous is not None:
        app.dependency_overrides[get_db] = previous
    else:
        app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def admin_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ADMIN_USERNAME", "hanin-ops")
    monkeypatch.setenv("ADMIN_PASSWORD", "test-admin-password")
    monkeypatch.setenv("ADMIN_SESSION_SECRET", "a" * 48)
    monkeypatch.setenv("IP_HASH_SECRET", "b" * 48)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _login(client: TestClient) -> None:
    response = client.post(
        "/v1/admin/login",
        json={"username": "hanin-ops", "password": "test-admin-password"},
    )
    assert response.status_code == 200
    assert "hanin_admin" in response.cookies


def _settings(**overrides: object) -> Settings:
    return Settings(
        database_url="sqlite+pysqlite:///:memory:",
        demo_offer_mapping_enabled=True,
        **overrides,
    )


def _order_payload(city: str | None = None) -> OrderCreate:
    return OrderCreate(
        full_name="مريم العلوي",
        phone="0612345678",
        city=city,
        items=[{"product_slug": "smart-baby-lamp", "offer_code": "OFFER_1"}],
    )


def test_login_rejected_when_admin_env_unset(client: TestClient) -> None:
    get_settings.cache_clear()
    response = client.post(
        "/v1/admin/login",
        json={"username": "anyone", "password": "nope"},
    )
    assert response.status_code == 503
    assert response.json()["code"] == "ADMIN_DISABLED"
    assert "Traceback" not in response.text


def test_login_success_and_me(client: TestClient, admin_env: None) -> None:
    wrong = client.post(
        "/v1/admin/login",
        json={"username": "hanin-ops", "password": "wrong-password"},
    )
    assert wrong.status_code == 401
    _login(client)
    me = client.get("/v1/admin/me")
    assert me.status_code == 200
    assert me.json()["username"] == "hanin-ops"
    logged_out = client.post("/v1/admin/logout")
    assert logged_out.status_code == 200
    denied = client.get("/v1/admin/me")
    assert denied.status_code == 401


def test_metrics_require_session(client: TestClient, admin_env: None) -> None:
    response = client.get("/v1/admin/metrics")
    assert response.status_code == 401


def test_metrics_exclude_vpn_and_non_ma(
    client: TestClient, admin_env: None, db_engine
) -> None:
    now = datetime.now(timezone.utc)
    with Session(db_engine, expire_on_commit=False) as db:
        db.add_all(
            [
                AnalyticsEvent(
                    path="/",
                    visitor_hash="v-ma",
                    ip_hash="i-ma",
                    country="MA",
                    vpn_flag=False,
                    proxy_flag=False,
                    anonymous_flag=False,
                    hosting_flag=False,
                    accepted=True,
                    source="first_party",
                    created_at=now,
                ),
                AnalyticsEvent(
                    path="/",
                    visitor_hash="v-vpn",
                    ip_hash="i-vpn",
                    country="MA",
                    vpn_flag=True,
                    proxy_flag=False,
                    anonymous_flag=True,
                    hosting_flag=False,
                    accepted=False,
                    source="first_party",
                    reject_reason="vpn",
                    created_at=now,
                ),
                AnalyticsEvent(
                    path="/",
                    visitor_hash="v-fr",
                    ip_hash="i-fr",
                    country="FR",
                    vpn_flag=False,
                    proxy_flag=False,
                    anonymous_flag=False,
                    hosting_flag=False,
                    accepted=False,
                    source="first_party",
                    reject_reason="non_ma",
                    created_at=now,
                ),
                AnalyticsEvent(
                    path="/products",
                    visitor_hash="v-unverified",
                    ip_hash="i-unverified",
                    country=None,
                    vpn_flag=None,
                    proxy_flag=None,
                    anonymous_flag=None,
                    hosting_flag=None,
                    accepted=False,
                    source="first_party",
                    reject_reason="unverified",
                    created_at=now,
                ),
            ]
        )
        db.commit()
    _login(client)
    metrics = client.get("/v1/admin/metrics")
    assert metrics.status_code == 200
    body = metrics.json()
    assert body["visits"] == 1
    assert body["unique_visitors"] == 1
    assert body["geo_detectors_configured"] is False
    assert "غير مُعد" in body["banner_ar"]
    assert "ip_hash" not in body
    assert body["conversion_basis"] == "unique_visitors"
    assert body["total_is_final"] is False


def test_order_list_and_optional_city(
    client: TestClient, admin_env: None, db_engine
) -> None:
    with Session(db_engine, expire_on_commit=False) as db:
        with_city = create_order(
            db, _order_payload(city="الدار البيضاء"), "admin-city-1", _settings()
        )
        without_city = create_order(
            db, _order_payload(city=None), "admin-city-2", _settings()
        )
        sandbox = create_order(
            db,
            _order_payload(city="الرباط"),
            "admin-city-3",
            _settings(sandbox_mode=True),
        )
    _login(client)
    listing = client.get("/v1/admin/orders")
    assert listing.status_code == 200
    refs = {row["public_reference"] for row in listing.json()["orders"]}
    assert with_city.response.public_reference in refs
    assert without_city.response.public_reference in refs
    assert sandbox.response.public_reference in refs
    preview = client.get(f"/v1/admin/orders/{with_city.response.public_reference}")
    assert preview.status_code == 200
    body = preview.json()
    assert body["city"] == "الدار البيضاء"
    assert body["full_name"] == "مريم العلوي"
    assert body["phone_e164"].startswith("+212")
    assert body["status"] == OrderStatus.PENDING.value
    assert body["status_readonly"] is True
    assert body["total_is_final"] is False
    empty_city = client.get(
        f"/v1/admin/orders/{without_city.response.public_reference}"
    )
    assert empty_city.json()["city"] is None
    search = client.get("/v1/admin/orders", params={"search": "مريم"})
    assert search.status_code == 200
    assert search.json()["total"] >= 1
    metrics = client.get("/v1/admin/metrics")
    cities = {row["city"]: row["orders"] for row in metrics.json()["orders_by_city"]}
    assert cities.get("الدار البيضاء", 0) >= 1
    assert None in cities or any(row["city"] is None for row in metrics.json()["orders_by_city"])


def test_events_view_never_breaks_and_excludes_unverified(
    client: TestClient, db_engine
) -> None:
    response = client.post("/v1/events/view", json={"path": "/"})
    assert response.status_code == 204
    bot = client.post(
        "/v1/events/view",
        json={"path": "/"},
        headers={"User-Agent": ""},
    )
    assert bot.status_code == 204
    with Session(db_engine, expire_on_commit=False) as db:
        accepted = db.scalar(
            select(AnalyticsEvent).where(AnalyticsEvent.accepted.is_(True))
        )
        assert accepted is None


def test_classifier_accepts_only_verified_morocco_non_vpn() -> None:
    settings = _settings()
    ma = classify_ip("8.8.8.8", settings, "MA")
    assert ma.verified is False
    assert is_accepted_morocco(ma) is False
    accepted = IpClassification(
        country="MA",
        is_vpn=False,
        is_proxy=False,
        is_anonymous=False,
        is_hosting=False,
        country_source="maxmind_country_db",
        vpn_source="maxmind_anonymous_ip_db",
    )
    vpn = IpClassification(
        country="MA",
        is_vpn=True,
        is_proxy=False,
        is_anonymous=True,
        is_hosting=False,
        country_source="maxmind_country_db",
        vpn_source="maxmind_anonymous_ip_db",
    )
    foreign = IpClassification(
        country="FR",
        is_vpn=False,
        is_proxy=False,
        is_anonymous=False,
        is_hosting=False,
        country_source="cloudflare_cf_ipcountry",
        vpn_source="maxmind_anonymous_ip_db",
    )
    assert is_accepted_morocco(accepted) is True
    assert is_accepted_morocco(vpn) is False
    assert is_accepted_morocco(foreign) is False
