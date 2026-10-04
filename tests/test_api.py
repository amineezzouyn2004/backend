from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from app.db.base import Base
from app.db.session import get_db
from app.main import app


engine = create_engine(
    "sqlite+pysqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
Base.metadata.create_all(engine)


def override_db():
    with Session(engine, expire_on_commit=False) as session:
        yield session


app.dependency_overrides[get_db] = override_db
client = TestClient(app)
item = {
    "product_slug": "smart-baby-nasal-aspirator",
    "offer_code": "OFFER_2",
}


def test_catalog_and_multi_quote_contracts() -> None:
    catalog = client.get("/v1/catalog/products")
    assert catalog.status_code == 200
    assert len(catalog.json()) == 3
    assert catalog.json()[0]["offer_mapping_mode"] == "development_demo"
    skus = {item["slug"]: item["sku"] for item in catalog.json()}
    assert skus == {
        "smart-baby-nasal-aspirator": "HNIN-ASP-001",
        "smart-baby-sleep-lamp": "HNIN-LMP-001",
        "natural-calming-baby-massage-oil": "HNIN-OIL-001",
    }
    quote = client.post("/v1/offers/quote", json={"items": [item]})
    assert quote.status_code == 200
    assert quote.json()["total_minor"] == 69_900
    assert quote.json()["total_is_final"] is False


def test_tampered_client_price_and_duplicate_product_are_rejected() -> None:
    tampered = client.post(
        "/v1/offers/quote",
        json={"items": [{**item, "line_total_minor": 1}], "currency": "USD"},
    )
    assert tampered.status_code == 422
    duplicate = client.post("/v1/offers/quote", json={"items": [item, item]})
    assert duplicate.status_code == 422
    assert duplicate.json()["code"] == "DUPLICATE_PRODUCT"


def test_upsell_tampering_rejected_when_disabled() -> None:
    response = client.post(
        "/v1/offers/quote",
        json={"items": [item], "upsell_intent": True},
    )
    assert response.status_code == 409
    assert response.json()["code"] == "UPSELL_UNAVAILABLE"


def test_create_order_and_public_confirmation_exclude_pii() -> None:
    created = client.post(
        "/v1/orders",
        headers={"Idempotency-Key": "api-key-123456"},
        json={"full_name": "مريم العلوي", "phone": "0612345678", "items": [item]},
    )
    assert created.status_code == 201
    body = created.json()
    assert "full_name" not in body
    assert "phone" not in body
    assert body["public_reference"].startswith("HNIN-MA-")
    assert created.headers["cache-control"] == "no-store"
    confirmation = client.get(f"/v1/orders/{body['public_reference']}")
    assert confirmation.status_code == 200
    assert confirmation.json() == body
    assert "no-store" in confirmation.headers["cache-control"]


def test_safe_validation_and_origin_protection() -> None:
    invalid = client.post(
        "/v1/orders",
        headers={"Idempotency-Key": "api-key-validation"},
        json={"full_name": "x", "phone": "no", "items": [item]},
    )
    assert invalid.status_code == 422
    assert invalid.json()["correlation_id"]
    origin = client.post(
        "/v1/orders",
        headers={"Idempotency-Key": "api-key-origin-check", "Origin": "https://untrusted.example"},
        json={"full_name": "مريم العلوي", "phone": "0612345678", "items": [item]},
    )
    assert origin.status_code == 403
