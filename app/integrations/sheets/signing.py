import base64
import hashlib
import hmac
import json
import time
from typing import Any


SIGNATURE_VERSION = "hmac-sha256-v1"


def canonical_payload_b64(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def sign_envelope(payload: dict[str, Any], secret: str, timestamp: int | None = None) -> dict[str, Any]:
    ts = timestamp or int(time.time())
    encoded = canonical_payload_b64(payload)
    signature = hmac.new(
        secret.encode(), f"{ts}.{encoded}".encode(), hashlib.sha256
    ).hexdigest()
    return {
        "signature_version": SIGNATURE_VERSION,
        "timestamp": ts,
        "payload_b64": encoded,
        "signature": signature,
    }


def verify_envelope(
    envelope: dict[str, Any],
    secret: str,
    *,
    now: int | None = None,
    max_age_seconds: int = 300,
) -> dict[str, Any]:
    if envelope.get("signature_version") != SIGNATURE_VERSION:
        raise ValueError("signature_version")
    timestamp = int(envelope["timestamp"])
    current = now or int(time.time())
    if abs(current - timestamp) > max_age_seconds:
        raise ValueError("timestamp")
    encoded = str(envelope["payload_b64"])
    expected = hmac.new(
        secret.encode(), f"{timestamp}.{encoded}".encode(), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(expected, str(envelope.get("signature", ""))):
        raise ValueError("signature")
    padding = "=" * (-len(encoded) % 4)
    return json.loads(base64.urlsafe_b64decode(encoded + padding))
