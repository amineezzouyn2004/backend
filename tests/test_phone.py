import pytest

from app.services.phone import (
    InvalidMoroccanPhone,
    format_moroccan_local_sheet,
    normalize_moroccan_mobile,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("0612345678", "+212612345678"),
        ("0712345678", "+212712345678"),
        ("+212612345678", "+212612345678"),
        ("+212712345678", "+212712345678"),
    ],
)
def test_normalizes_moroccan_mobile(raw: str, expected: str) -> None:
    assert normalize_moroccan_mobile(raw) == expected


@pytest.mark.parametrize(
    ("e164", "local"),
    [
        ("+212612345678", "0612345678"),
        ("+212712345678", "0712345678"),
    ],
)
def test_sheet_phone_is_local_without_changing_e164(e164: str, local: str) -> None:
    assert format_moroccan_local_sheet(e164) == local
    assert normalize_moroccan_mobile(local) == e164


@pytest.mark.parametrize("raw", ["", "not a phone", "0512345678", "+33123456789"])
def test_rejects_invalid_or_non_mobile(raw: str) -> None:
    with pytest.raises(InvalidMoroccanPhone):
        normalize_moroccan_mobile(raw)
