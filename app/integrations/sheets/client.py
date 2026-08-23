from dataclasses import dataclass
from typing import Any

import httpx

from app.integrations.sheets.signing import sign_envelope


@dataclass(frozen=True)
class SheetsDeliveryResult:
    delivered: bool
    retryable: bool
    error_code: str | None = None


class SheetsWebhookClient:
    def __init__(self, url: str, secret: str, timeout_seconds: float = 8.0):
        self.url = url
        self.secret = secret
        self.timeout_seconds = timeout_seconds

    def deliver(self, payload: dict[str, Any]) -> SheetsDeliveryResult:
        try:
            response = httpx.post(
                self.url,
                json=sign_envelope(payload, self.secret),
                timeout=self.timeout_seconds,
                follow_redirects=True,
            )
        except (httpx.TimeoutException, httpx.NetworkError):
            return SheetsDeliveryResult(False, True, "network_error")
        if response.status_code >= 500 or response.status_code == 429:
            return SheetsDeliveryResult(False, True, f"http_{response.status_code}")
        if response.status_code >= 400:
            return SheetsDeliveryResult(False, False, f"http_{response.status_code}")
        try:
            body = response.json()
        except ValueError:
            return SheetsDeliveryResult(False, False, "invalid_response")
        if body.get("ok") is True:
            return SheetsDeliveryResult(True, False)
        return SheetsDeliveryResult(False, body.get("retryable") is True, str(body.get("code", "rejected")))
