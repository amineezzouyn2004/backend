import logging
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db.session import SessionLocal
from app.integrations.minfraud import (
    MinFraudGateway,
    is_minfraud_ready,
    store_assessment,
)
from app.integrations.sheets import SheetsWebhookClient
from app.models.tracking import DeliveryStatus, OutboxEvent


logger = logging.getLogger("hanin.worker")


def _apply_result(
    event: OutboxEvent,
    *,
    delivered: bool,
    retryable: bool,
    error_code: str | None,
    max_attempts: int,
) -> None:
    event.attempts += 1
    if delivered:
        event.status = DeliveryStatus.SENT
        event.sent_at = datetime.now(timezone.utc)
        event.last_error_code = None
        return
    if retryable and event.attempts < max_attempts:
        event.status = DeliveryStatus.FAILED
        event.last_error_code = error_code
        delay = min(3600, 2 ** event.attempts * 15)
        event.next_attempt_at = datetime.now(timezone.utc) + timedelta(seconds=delay)
        return
    event.status = DeliveryStatus.DEAD
    event.last_error_code = error_code


def process_outbox(
    db: Session,
    settings: Settings,
    *,
    minfraud_gateway: MinFraudGateway | None = None,
) -> int:
    events = db.scalars(
        select(OutboxEvent)
        .where(
            OutboxEvent.status.in_([DeliveryStatus.PENDING, DeliveryStatus.FAILED]),
            (OutboxEvent.next_attempt_at.is_(None))
            | (OutboxEvent.next_attempt_at <= datetime.now(timezone.utc)),
        )
        .order_by(OutboxEvent.created_at)
        .limit(20)
    ).all()
    processed = 0
    for event in events:
        if event.destination == "sheets":
            if not settings.sheets_webhook_enabled:
                continue
            client = SheetsWebhookClient(
                settings.sheets_webhook_url or "",
                settings.sheets_webhook_secret or "",
                settings.sheets_timeout_seconds,
            )
            result = client.deliver(event.payload)
            _apply_result(
                event,
                delivered=result.delivered,
                retryable=result.retryable,
                error_code=result.error_code,
                max_attempts=settings.outbox_max_attempts,
            )
            processed += 1
            continue
        if event.destination == "minfraud":
            if not is_minfraud_ready(settings):
                continue
            gateway = minfraud_gateway or MinFraudGateway.from_settings(settings)
            result = gateway.assess(event.payload)
            if result.delivered:
                store_assessment(
                    db,
                    order_id=event.aggregate_id,
                    service=gateway.service,
                    result=result,
                )
            _apply_result(
                event,
                delivered=result.delivered,
                retryable=result.retryable,
                error_code=result.error_code,
                max_attempts=settings.outbox_max_attempts,
            )
            processed += 1
    db.commit()
    if processed:
        logger.info("processed_outbox count=%s", processed)
    return processed


def process_once() -> int:
    settings = get_settings()
    with SessionLocal() as db:
        return process_outbox(db, settings)


def main() -> None:
    settings = get_settings()
    while True:
        process_once()
        time.sleep(settings.outbox_poll_seconds)


if __name__ == "__main__":
    main()
