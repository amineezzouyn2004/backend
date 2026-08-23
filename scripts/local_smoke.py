"""Repeatable local HTTP smoke test for Hanin.

Requires migrated backend and built/running frontend. Uses synthetic local-only
data and never contacts external integrations.
"""

from __future__ import annotations

import os
import uuid

import httpx


API_URL = os.getenv("HANIN_SMOKE_API_URL", "http://127.0.0.1:8000")
FRONTEND_URL = os.getenv("HANIN_SMOKE_FRONTEND_URL", "http://127.0.0.1:3000")
ORIGIN = FRONTEND_URL
TIMEOUT = 10.0

ITEM = {
    "product_slug": "smart-baby-nasal-aspirator",
    "offer_code": "OFFER_2",
}


def require(response: httpx.Response, status: int, label: str) -> dict:
    assert response.status_code == status, (
        f"{label}: expected {status}, got {response.status_code}: "
        f"{response.text[:500]}"
    )
    content_type = response.headers.get("content-type", "").split(";", 1)[0]
    if content_type == "application/json" or content_type.endswith("+json"):
        return response.json()
    return {}


def assert_security_headers(response: httpx.Response, label: str) -> None:
    assert response.headers.get("x-content-type-options") == "nosniff", label
    assert response.headers.get("referrer-policy") == "strict-origin-when-cross-origin", label
    assert response.headers.get("content-security-policy"), label


def main() -> None:
    with httpx.Client(timeout=TIMEOUT, follow_redirects=False) as client:
        live = client.get(f"{API_URL}/health/live")
        require(live, 200, "health/live")
        assert_security_headers(live, "API security headers")
        require(client.get(f"{API_URL}/health/ready"), 200, "health/ready")

        catalog = require(client.get(f"{API_URL}/v1/catalog/products"), 200, "catalog")
        assert len(catalog) == 3
        assert all(item["offer_mapping_mode"] == "development_demo" for item in catalog)

        offers = require(client.get(f"{API_URL}/v1/offers"), 200, "offers")
        assert [offer["total_minor"] for offer in offers] == [39_900, 69_900, 94_900]
        assert [offer["saving_minor"] for offer in offers] == [0, 9_900, 24_800]

        quote = require(
            client.post(f"{API_URL}/v1/offers/quote", json={"items": [ITEM]}),
            200,
            "quote",
        )
        assert quote["total_minor"] == 69_900
        assert quote["total_is_final"] is False

        tampered = require(
            client.post(
                f"{API_URL}/v1/offers/quote",
                json={"items": [{**ITEM, "line_total_minor": 1}], "currency": "USD"},
            ),
            422,
            "tampered quote",
        )
        assert tampered["code"] == "VALIDATION_FAILED"

        duplicate = require(
            client.post(f"{API_URL}/v1/offers/quote", json={"items": [ITEM, ITEM]}),
            422,
            "duplicate product",
        )
        assert duplicate["code"] == "DUPLICATE_PRODUCT"

        upsell = require(
            client.post(
                f"{API_URL}/v1/offers/quote",
                json={"items": [ITEM], "upsell_intent": True},
            ),
            409,
            "disabled upsell",
        )
        assert upsell["code"] == "UPSELL_UNAVAILABLE"

        key = f"phase5-{uuid.uuid4()}"
        payload = {
            "full_name": "اختبار محلي",
            "phone": "0612345678",
            "items": [ITEM],
        }
        headers = {"Idempotency-Key": key, "Origin": ORIGIN}
        created_response = client.post(f"{API_URL}/v1/orders", headers=headers, json=payload)
        created = require(created_response, 201, "create order")
        assert created_response.headers["idempotency-replayed"] == "false"
        assert created_response.headers["cache-control"] == "no-store"
        assert created["status"] == "pending"
        assert created["total_minor"] == 69_900
        assert created["total_is_final"] is False
        assert "full_name" not in created and "phone" not in created

        replay_response = client.post(f"{API_URL}/v1/orders", headers=headers, json=payload)
        replay = require(replay_response, 201, "idempotent replay")
        assert replay_response.headers["idempotency-replayed"] == "true"
        assert replay == created

        conflict = require(
            client.post(
                f"{API_URL}/v1/orders",
                headers=headers,
                json={**payload, "full_name": "اختبار مختلف"},
            ),
            409,
            "idempotency conflict",
        )
        assert conflict["code"] == "IDEMPOTENCY_CONFLICT"
        assert "اختبار محلي" not in str(conflict)

        reference = created["public_reference"]
        confirmation_response = client.get(f"{API_URL}/v1/orders/{reference}")
        confirmation = require(confirmation_response, 200, "public confirmation")
        assert confirmation == created
        assert "no-store" in confirmation_response.headers["cache-control"]
        require(
            client.get(f"{API_URL}/v1/orders/not-a-real-reference"),
            404,
            "unknown reference",
        )

        rejected_origin = require(
            client.post(
                f"{API_URL}/v1/orders",
                headers={"Idempotency-Key": f"phase5-{uuid.uuid4()}", "Origin": "https://invalid.example"},
                json=payload,
            ),
            403,
            "origin rejection",
        )
        assert rejected_origin["code"] == "ORIGIN_NOT_ALLOWED"

        oversized = require(
            client.post(
                f"{API_URL}/v1/orders",
                headers={
                    "Idempotency-Key": f"phase5-{uuid.uuid4()}",
                    "Origin": ORIGIN,
                    "Content-Type": "application/json",
                },
                content=b'{"padding":"' + (b"x" * 33_000) + b'"}',
            ),
            413,
            "body limit",
        )
        assert oversized["code"] == "REQUEST_TOO_LARGE"

        preflight = client.options(
            f"{API_URL}/v1/orders",
            headers={
                "Origin": ORIGIN,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type,idempotency-key",
            },
        )
        require(preflight, 200, "CORS preflight")
        assert preflight.headers["access-control-allow-origin"] == ORIGIN

        frontend_paths = [
            "/",
            "/products",
            "/products/smart-baby-nasal-aspirator",
            "/checkout",
            "/privacy",
            "/robots.txt",
            "/sitemap.xml",
        ]
        for path in frontend_paths:
            response = client.get(f"{FRONTEND_URL}{path}")
            require(response, 200, f"frontend {path}")
            assert_security_headers(response, f"frontend headers {path}")

        home = client.get(FRONTEND_URL)
        assert '<html lang="ar" dir="rtl"' in home.text
        assert "حـنـيـن" in home.text
        assert "aggregateRating" not in home.text

        frontend_confirmation = client.get(f"{FRONTEND_URL}/order/{reference}")
        require(frontend_confirmation, 200, "frontend confirmation")
        assert reference in frontend_confirmation.text
        assert "معلّق" in frontend_confirmation.text

        missing = client.get(f"{FRONTEND_URL}/order/not-a-real-reference")
        require(missing, 200, "safe unknown frontend confirmation")
        assert "تعذر تحميل الطلب" in missing.text

    print("PHASE5_LOCAL_SMOKE_OK")


if __name__ == "__main__":
    main()
