import json
import time

import httpx
import pytest

from datetime import datetime, timezone

from app.integrations.sheets.client import SheetsWebhookClient
from app.integrations.sheets.payload import (
    SHEET_HEADERS,
    build_sheets_payload,
    format_sheet_date,
)
from app.integrations.sheets.signing import sign_envelope, verify_envelope


def test_signed_envelope_round_trip_and_tamper_rejection() -> None:
    payload = {"event_id": "evt-1", "total_minor": 39_900}
    envelope = sign_envelope(payload, "secret", timestamp=1_000)
    assert verify_envelope(envelope, "secret", now=1_100) == payload
    envelope["payload_b64"] += "x"
    with pytest.raises(ValueError, match="signature"):
        verify_envelope(envelope, "secret", now=1_100)


def test_replay_window_rejected() -> None:
    envelope = sign_envelope({"event_id": "evt"}, "secret", timestamp=1_000)
    with pytest.raises(ValueError, match="timestamp"):
        verify_envelope(envelope, "secret", now=1_301)


def test_client_understands_apps_script_safe_body(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_post(*args: object, **kwargs: object) -> httpx.Response:
        envelope = kwargs["json"]
        payload = verify_envelope(envelope, "secret", now=int(time.time()))
        assert payload["event_id"] == "evt-1"
        return httpx.Response(200, json={"ok": True, "duplicate": False})

    monkeypatch.setattr(httpx, "post", fake_post)
    result = SheetsWebhookClient("https://example.invalid/exec", "secret").deliver(
        {"event_id": "evt-1"}
    )
    assert result.delivered is True


def test_sheets_payload_matches_csv_headers_and_blank_status() -> None:
    created = datetime(2026, 10, 2, 10, 30, tzinfo=timezone.utc)
    payload = build_sheets_payload(
        event_id="evt-sheet-1",
        public_reference="HNIN-MA-abc123",
        created_at=created,
        full_name="مريم العلوي",
        phone_e164="+212687984567",
        product_names_ar=["شفّاط الأنف الذكي للرضّع", "مصباح النوم الذكي بالصوت والحركة"],
        skus=["HNIN-ASP-001", "HNIN-LMP-001"],
        quantities=[2, 2],
        total_minor=139_800,
    )
    for header in SHEET_HEADERS:
        assert header in payload
    assert payload["date"] == format_sheet_date(created)
    assert payload["date"] == "02/10/2026"
    assert payload["order id"] == "HNIN-MA-abc123"
    assert payload["country"] == "Morocco"
    assert payload["name"] == "مريم العلوي"
    assert payload["phone"] == "0687984567"
    assert payload["product"] == (
        "شفّاط الأنف الذكي للرضّع/مصباح النوم الذكي بالصوت والحركة"
    )
    assert payload["sku"] == "HNIN-ASP-001/HNIN-LMP-001"
    assert payload["quantity"] == "2/2"
    assert payload["total price"] == "1398.00"
    assert payload["currency"] == "MAD"
    assert payload["status"] == ""
    assert payload["schema_version"] == 3
    assert "order_status" not in payload
