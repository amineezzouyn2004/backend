from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class NoOpDeliveryResult:
    event_id: UUID
    delivered: bool = False
    reason: str = "tracking_disabled"


class NoOpTrackingAdapter:
    enabled = False

    def deliver(self, event_id: UUID) -> NoOpDeliveryResult:
        return NoOpDeliveryResult(event_id=event_id)
