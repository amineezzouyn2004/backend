from datetime import datetime, timezone

from app.models.order import Order, OrderStatus, OrderStatusHistory


ALLOWED_TRANSITIONS: dict[OrderStatus, frozenset[OrderStatus]] = {
    OrderStatus.PENDING: frozenset({OrderStatus.CONFIRMED, OrderStatus.CANCELLED}),
    OrderStatus.CONFIRMED: frozenset({OrderStatus.PROCESSING, OrderStatus.CANCELLED}),
    OrderStatus.PROCESSING: frozenset({OrderStatus.SHIPPED, OrderStatus.CANCELLED}),
    OrderStatus.SHIPPED: frozenset({OrderStatus.OUT_FOR_DELIVERY, OrderStatus.RETURNED}),
    OrderStatus.OUT_FOR_DELIVERY: frozenset({OrderStatus.DELIVERED, OrderStatus.RETURNED}),
    OrderStatus.DELIVERED: frozenset({OrderStatus.RETURNED}),
    OrderStatus.CANCELLED: frozenset(),
    OrderStatus.RETURNED: frozenset(),
}


class InvalidTransition(ValueError):
    pass


def transition_order(
    order: Order,
    target: OrderStatus,
    *,
    reason_code: str,
    actor_type: str,
    actor_id: str | None = None,
) -> OrderStatusHistory:
    if target not in ALLOWED_TRANSITIONS[order.status]:
        raise InvalidTransition(f"{order.status.value}->{target.value}")
    if target is OrderStatus.CONFIRMED and not order.total_is_final:
        raise InvalidTransition("confirmation requires final address/shipping/tax")
    previous = order.status
    now = datetime.now(timezone.utc)
    order.status = target
    timestamp_fields = {
        OrderStatus.CONFIRMED: "confirmed_at",
        OrderStatus.SHIPPED: "shipped_at",
        OrderStatus.DELIVERED: "delivered_at",
        OrderStatus.CANCELLED: "cancelled_at",
        OrderStatus.RETURNED: "returned_at",
    }
    if field := timestamp_fields.get(target):
        setattr(order, field, now)
    history = OrderStatusHistory(
        order=order,
        from_status=previous,
        to_status=target,
        reason_code=reason_code,
        actor_type=actor_type,
        actor_id=actor_id,
        safe_metadata={},
        occurred_at=now,
    )
    return history
