from datetime import datetime, timezone
from typing import Any, Iterable
from zoneinfo import ZoneInfo

from app.services.phone import format_moroccan_local_sheet

# Sheet `date` uses Morocco civil time (Africa/Casablanca), not a delivery date.
SHEET_DATE_TZ = ZoneInfo("Africa/Casablanca")
SHEETS_SCHEMA_VERSION = 3
SHEET_HEADERS = (
    "date",
    "order id",
    "country",
    "name",
    "phone",
    "product",
    "sku",
    "quantity",
    "total price",
    "currency",
    "status",
)
PUBLIC_REFERENCE_PREFIX = "HNIN-MA-"


def format_sheet_date(created_at: datetime | None) -> str:
    moment = created_at or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(SHEET_DATE_TZ).strftime("%d/%m/%Y")


def format_total_price_major(total_minor: int) -> str:
    return f"{total_minor / 100:.2f}"


def join_sheet_values(values: Iterable[object]) -> str:
    return "/".join(str(value) for value in values)


def build_sheets_payload(
    *,
    event_id: str,
    public_reference: str,
    created_at: datetime | None,
    full_name: str,
    phone_e164: str,
    product_names_ar: list[str],
    skus: list[str],
    quantities: list[int],
    total_minor: int,
) -> dict[str, Any]:
    return {
        "schema_version": SHEETS_SCHEMA_VERSION,
        "event_id": event_id,
        "date": format_sheet_date(created_at),
        "order id": public_reference,
        "country": "Morocco",
        "name": full_name,
        "phone": format_moroccan_local_sheet(phone_e164),
        "product": join_sheet_values(product_names_ar),
        "sku": join_sheet_values(skus),
        "quantity": join_sheet_values(quantities),
        "total price": format_total_price_major(total_minor),
        "currency": "MAD",
        "status": "",
    }
