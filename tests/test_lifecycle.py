import uuid

import pytest

from app.models.order import Order, OrderStatus
from app.services.lifecycle import InvalidTransition, transition_order


def order(status: OrderStatus = OrderStatus.PENDING, final: bool = True) -> Order:
    return Order(
        id=uuid.uuid4(),
        public_reference="opaque",
        status=status,
        full_name="test",
        phone_e164="+212612345678",
        currency="MAD",
        subtotal_minor=100,
        discount_minor=0,
        total_minor=100,
        total_is_final=final,
        offer_code="OFFER_1",
        offer_version=1,
    )


def test_full_allowed_lifecycle() -> None:
    current = order()
    for target in [
        OrderStatus.CONFIRMED,
        OrderStatus.PROCESSING,
        OrderStatus.SHIPPED,
        OrderStatus.OUT_FOR_DELIVERY,
        OrderStatus.DELIVERED,
        OrderStatus.RETURNED,
    ]:
        history = transition_order(
            current,
            target,
            reason_code="test",
            actor_type="system",
        )
        assert history.to_status == target
        assert current.status == target


def test_invalid_transition_and_incomplete_confirmation_blocked() -> None:
    with pytest.raises(InvalidTransition):
        transition_order(
            order(),
            OrderStatus.SHIPPED,
            reason_code="invalid",
            actor_type="system",
        )
    with pytest.raises(InvalidTransition):
        transition_order(
            order(final=False),
            OrderStatus.CONFIRMED,
            reason_code="no_address",
            actor_type="system",
        )
