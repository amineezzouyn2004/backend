"""Official minFraud Python client wrapper. Never logs PII or credentials."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol
from uuid import UUID

from minfraud import Client
from minfraud.errors import (
    AuthenticationError,
    HTTPError,
    InsufficientFundsError,
    InvalidRequestError,
    PermissionRequiredError,
)
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.models.minfraud import MinFraudAssessment

from .payload import ALLOWED_MINFRAUD_HOSTS, build_report, build_transaction

logger = logging.getLogger("hanin.minfraud")


class MinFraudClientProtocol(Protocol):
    def score(self, transaction: dict[str, Any]) -> Any: ...
    def insights(self, transaction: dict[str, Any]) -> Any: ...
    def factors(self, transaction: dict[str, Any]) -> Any: ...
    def report(self, report: dict[str, Any]) -> Any: ...


@dataclass(frozen=True)
class MinFraudDeliveryResult:
    delivered: bool
    retryable: bool
    error_code: str | None = None
    minfraud_id: str | None = None
    risk_score: float | None = None
    disposition_action: str | None = None
    disposition_reason: str | None = None
    disposition_rule_label: str | None = None
    ip_risk: float | None = None
    warning_codes: list[str] = field(default_factory=list)
    risk_reason_codes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class MinFraudReportResult:
    delivered: bool
    retryable: bool
    error_code: str | None = None


def _codes_from_warnings(response: Any) -> list[str]:
    codes: list[str] = []
    for warning in getattr(response, "warnings", None) or []:
        code = getattr(warning, "code", None)
        if code:
            codes.append(str(code))
    return codes


def _codes_from_risk_reasons(response: Any) -> list[str]:
    codes: list[str] = []
    for group in getattr(response, "risk_score_reasons", None) or []:
        for reason in getattr(group, "reasons", None) or []:
            code = getattr(reason, "code", None)
            if code:
                codes.append(str(code))
    return codes


def _from_response(response: Any) -> MinFraudDeliveryResult:
    disposition = getattr(response, "disposition", None)
    ip_address = getattr(response, "ip_address", None)
    return MinFraudDeliveryResult(
        delivered=True,
        retryable=False,
        minfraud_id=str(getattr(response, "id")),
        risk_score=float(getattr(response, "risk_score")),
        disposition_action=getattr(disposition, "action", None) if disposition else None,
        disposition_reason=getattr(disposition, "reason", None) if disposition else None,
        disposition_rule_label=(
            getattr(disposition, "rule_label", None) if disposition else None
        ),
        ip_risk=(
            float(ip_address.risk)
            if ip_address is not None and getattr(ip_address, "risk", None) is not None
            else None
        ),
        warning_codes=_codes_from_warnings(response),
        risk_reason_codes=_codes_from_risk_reasons(response),
    )


def _error_code_for(exc: BaseException) -> str:
    if isinstance(exc, AuthenticationError):
        return "authentication_error"
    if isinstance(exc, InsufficientFundsError):
        return "insufficient_funds"
    if isinstance(exc, PermissionRequiredError):
        return "permission_required"
    if isinstance(exc, InvalidRequestError):
        return "invalid_request"
    if isinstance(exc, HTTPError):
        return f"http_{exc.http_status}" if exc.http_status else "network_error"
    return "network_error"


def _classify_exception(exc: BaseException) -> MinFraudDeliveryResult:
    error_code = _error_code_for(exc)
    if isinstance(
        exc,
        (
            AuthenticationError,
            InsufficientFundsError,
            PermissionRequiredError,
            InvalidRequestError,
        ),
    ):
        return MinFraudDeliveryResult(False, False, error_code)
    if isinstance(exc, HTTPError):
        status = exc.http_status
        retryable = status is None or status >= 500 or status == 429
        return MinFraudDeliveryResult(False, retryable, error_code)
    return MinFraudDeliveryResult(False, True, error_code)


class MinFraudGateway:
    def __init__(
        self,
        account_id: int,
        license_key: str,
        *,
        service: str = "score",
        timeout_seconds: float = 8.0,
        host: str = "minfraud.maxmind.com",
        client: MinFraudClientProtocol | None = None,
    ):
        if host not in ALLOWED_MINFRAUD_HOSTS:
            raise ValueError("minfraud_host_not_allowed")
        if service not in {"score", "insights", "factors"}:
            raise ValueError("minfraud_service_not_allowed")
        self.service = service
        self._client = client or Client(
            account_id, license_key, host=host, timeout=timeout_seconds
        )

    @classmethod
    def from_settings(
        cls,
        settings: Settings,
        client: MinFraudClientProtocol | None = None,
    ) -> MinFraudGateway:
        account_id = settings.maxmind_account_id_int
        license_key = settings.maxmind_license_key_value
        if account_id is None or license_key is None:
            raise ValueError("minfraud_credentials_missing")
        return cls(
            account_id,
            license_key,
            service=settings.maxmind_minfraud_service,
            timeout_seconds=settings.maxmind_minfraud_timeout_seconds,
            host=settings.maxmind_minfraud_host,
            client=client,
        )

    def assess(self, payload: dict[str, Any]) -> MinFraudDeliveryResult:
        transaction = build_transaction(payload)
        method = getattr(self._client, self.service)
        try:
            response = method(transaction)
        except Exception as exc:  # noqa: BLE001 — classified; never re-raise to order path
            logger.warning("minfraud_assess_failed error_code=%s", type(exc).__name__)
            return _classify_exception(exc)
        result = _from_response(response)
        logger.info(
            "minfraud_assessed service=%s minfraud_id=%s risk_score=%s",
            self.service,
            result.minfraud_id,
            result.risk_score,
        )
        return result

    def report_transaction(
        self,
        *,
        tag: str,
        minfraud_id: str | None = None,
        transaction_id: str | None = None,
        notes: str | None = None,
        chargeback_code: str | None = None,
    ) -> MinFraudReportResult:
        """Report a previously scored transaction. Not a public HTTP endpoint.

        Lifecycle auto-mapping is intentionally not wired: cancelled/returned/
        delivered do not have a verified official tag mapping for COD.
        """
        try:
            document = build_report(
                tag=tag,
                minfraud_id=minfraud_id,
                transaction_id=transaction_id,
                notes=notes,
                chargeback_code=chargeback_code,
            )
        except ValueError as exc:
            return MinFraudReportResult(False, False, str(exc))
        try:
            self._client.report(document)
        except Exception as exc:  # noqa: BLE001
            classified = _classify_exception(exc)
            logger.warning("minfraud_report_failed error_code=%s", classified.error_code)
            return MinFraudReportResult(
                False, classified.retryable, classified.error_code
            )
        logger.info("minfraud_reported tag=%s", tag)
        return MinFraudReportResult(True, False)


def store_assessment(
    db: Session,
    *,
    order_id: UUID,
    service: str,
    result: MinFraudDeliveryResult,
) -> MinFraudAssessment:
    existing = db.scalar(
        select(MinFraudAssessment).where(MinFraudAssessment.order_id == order_id)
    )
    now = datetime.now(timezone.utc) if result.delivered else None
    if existing is None:
        existing = MinFraudAssessment(order_id=order_id, service=service)
        db.add(existing)
    existing.service = service
    existing.minfraud_id = result.minfraud_id
    existing.risk_score = result.risk_score
    existing.disposition_action = result.disposition_action
    existing.disposition_reason = result.disposition_reason
    existing.disposition_rule_label = result.disposition_rule_label
    existing.ip_risk = result.ip_risk
    existing.warning_codes = list(result.warning_codes)
    existing.risk_reason_codes = list(result.risk_reason_codes)
    existing.error_code = result.error_code
    existing.assessed_at = now
    return existing
