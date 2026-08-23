import hashlib
import uuid

import pytest

from app.integrations.tracking import NoOpTrackingAdapter
from app.integrations.tracking.hashing import (
    hash_meta_phone, hash_snap_phone, hash_tiktok_phone,
)
from app.integrations.tracking.mapping import map_event


def test_noop_adapter_never_delivers() -> None:
    event_id = uuid.uuid4()
    result = NoOpTrackingAdapter().deliver(event_id)
    assert result.event_id == event_id
    assert result.delivered is False


def test_provider_specific_mappings_and_no_purchase_default() -> None:
    assert map_event("ProductViewed", "meta") == "ViewContent"
    assert map_event("CheckoutStarted", "snap") == "START_CHECKOUT"
    assert map_event("OrderSubmitted", "meta") is None


def test_platform_hashing_is_separate_and_refuses_double_hash() -> None:
    phone = "+212612345678"
    assert hash_meta_phone(phone) == hashlib.sha256(b"212612345678").hexdigest()
    assert hash_snap_phone(phone) == hashlib.sha256(b"212612345678").hexdigest()
    assert hash_tiktok_phone(phone) == hashlib.sha256(phone.encode()).hexdigest()
    with pytest.raises(ValueError, match="already_hashed"):
        hash_meta_phone("a" * 64)
