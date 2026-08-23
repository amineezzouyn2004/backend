import json
import time

import httpx
import pytest

from app.integrations.sheets.client import SheetsWebhookClient
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
