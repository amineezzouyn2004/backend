"""Build minFraud request documents from Hanin order data.

Follows official minFraud v2.0 request fields only. Does not hash inputs;
MaxMind hashes internally. Does not invent email, address, or card data.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import phonenumbers

from app.config import Settings

MINOR_UNITS = Decimal(100)
OFFICIAL_REPORT_TAGS = frozenset(
    {"not_fraud", "suspected_fraud", "spam_or_abuse", "chargeback", "clear"}
)
ALLOWED_MINFRAUD_HOSTS = frozenset({"minfraud.maxmind.com", "sandbox.maxmind.com"})


def is_minfraud_ready(settings: Settings) -> bool:
    return (
        settings.maxmind_minfraud_enabled
        and settings.maxmind_account_id_int is not None
        and settings.maxmind_license_key_value is not None
    )


def minor_to_decimal(minor: int) -> float:
    return float(Decimal(minor) / MINOR_UNITS)


def split_person_name(full_name: str) -> tuple[str | None, str | None]:
    parts = full_name.split()
    if not parts:
        return None, None
    if len(parts) == 1:
        return parts[0], None
    return parts[0], " ".join(parts[1:])


def phone_country_and_national(phone_e164: str) -> tuple[str, str] | None:
    try:
        parsed = phonenumbers.parse(phone_e164, None)
    except phonenumbers.NumberParseException:
        return None
    if not parsed.country_code or not parsed.national_number:
        return None
    return str(parsed.country_code), str(parsed.national_number)


def build_outbox_payload(
    *,
    order_id: str,
    public_reference: str,
    full_name: str,
    phone_e164: str,
    subtotal_minor: int,
    discount_minor: int,
    total_minor: int,
    currency: str,
    offer_code: str | None,
    created_at: str | None,
    client_ip: str | None,
    user_agent: str | None,
    accept_language: str | None,
    items: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "order_id": order_id,
        "order_public_reference": public_reference,
        "full_name": full_name,
        "phone_e164": phone_e164,
        "subtotal_minor": subtotal_minor,
        "discount_minor": discount_minor,
        "total_minor": total_minor,
        "currency": currency,
        "offer_code": offer_code,
        "created_at": created_at,
        "client_ip": client_ip,
        "user_agent": user_agent,
        "accept_language": accept_language,
        "items": items,
    }


def build_transaction(payload: dict[str, Any]) -> dict[str, Any]:
    """Map an outbox payload to the official minFraud request object.

    Payment method is omitted: official enums have no COD/cash value
    (bank_debit, bank_redirect, bank_transfer, buy_now_pay_later, card,
    crypto, digital_wallet, gift_card, real_time_payment, rewards). Sending
    a mismatched method would be inaccurate. Address, email, and credit_card
    are omitted because Hanin does not collect them.
    """
    transaction: dict[str, Any] = {
        "event": {
            "transaction_id": payload["order_public_reference"],
            "type": "purchase",
            "party": "customer",
        },
        "order": {
            # Official /order/amount: total before taxes and discounts.
            "amount": minor_to_decimal(int(payload["subtotal_minor"])),
            "currency": payload["currency"],
        },
    }
    created_at = payload.get("created_at")
    if created_at:
        transaction["event"]["time"] = created_at
    if payload.get("offer_code"):
        transaction["order"]["discount_code"] = payload["offer_code"]

    device: dict[str, Any] = {}
    if payload.get("client_ip"):
        device["ip_address"] = payload["client_ip"]
    user_agent = payload.get("user_agent")
    if user_agent:
        device["user_agent"] = str(user_agent)[:512]
    accept_language = payload.get("accept_language")
    if accept_language:
        device["accept_language"] = str(accept_language)[:255]
    if device:
        transaction["device"] = device

    first_name, last_name = split_person_name(str(payload.get("full_name") or ""))
    phone_parts = phone_country_and_national(str(payload.get("phone_e164") or ""))
    person: dict[str, Any] = {}
    if first_name:
        person["first_name"] = first_name
    if last_name:
        person["last_name"] = last_name
    if phone_parts:
        person["phone_country_code"] = phone_parts[0]
        person["phone_number"] = phone_parts[1]
    if person:
        # COD: billing and shipping contact are the same collected name/phone.
        # No street/city/postal is sent; those are not collected yet.
        transaction["billing"] = dict(person)
        transaction["shipping"] = dict(person)

    cart: list[dict[str, Any]] = []
    for item in payload.get("items") or []:
        item_id = item.get("item_id")
        quantity = item.get("quantity")
        unit_minor = item.get("unit_minor")
        if not item_id or quantity is None or unit_minor is None:
            continue
        cart.append(
            {
                "item_id": str(item_id)[:255],
                "quantity": int(quantity),
                "price": minor_to_decimal(int(unit_minor)),
            }
        )
    if cart:
        transaction["shopping_cart"] = cart
    return transaction


def build_report(
    *,
    tag: str,
    minfraud_id: str | None = None,
    transaction_id: str | None = None,
    notes: str | None = None,
    chargeback_code: str | None = None,
) -> dict[str, Any]:
    if tag not in OFFICIAL_REPORT_TAGS:
        raise ValueError("invalid_minfraud_report_tag")
    report: dict[str, Any] = {"tag": tag}
    if minfraud_id:
        report["minfraud_id"] = minfraud_id
    if transaction_id:
        report["transaction_id"] = transaction_id
    if notes:
        report["notes"] = notes[:1000]
    if chargeback_code:
        report["chargeback_code"] = chargeback_code
    if "minfraud_id" not in report and "transaction_id" not in report:
        raise ValueError("minfraud_report_identifier_required")
    return report
