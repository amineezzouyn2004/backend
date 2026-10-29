from __future__ import annotations

from datetime import datetime

from typing import Any

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.models.order import Order, OrderItem, OrderStatus, OrderStatusHistory
from app.services.admin_metrics import casablanca_range
from app.services.phone import InvalidMoroccanPhone, normalize_moroccan_mobile


def _sandbox_flag(history: list[OrderStatusHistory]) -> bool:
    return any((entry.safe_metadata or {}).get("sandbox") is True for entry in history)


def _city(history: list[OrderStatusHistory]) -> str | None:
    for entry in history:
        city = (entry.safe_metadata or {}).get("city")
        if isinstance(city, str) and city.strip():
            return city.strip()
    return None


def _apply_filters(
    stmt: Select[Any],
    *,
    status: str | None,
    search: str | None,
    start: datetime | None,
    end: datetime | None,
) -> Select[Any]:
    if start is not None:
        stmt = stmt.where(Order.created_at >= start)
    if end is not None:
        stmt = stmt.where(Order.created_at < end)
    if status:
        try:
            parsed = OrderStatus(status)
        except ValueError:
            parsed = None
        if parsed is not None:
            stmt = stmt.where(Order.status == parsed)
    needle = (search or "").strip()
    if needle:
        pattern = f"%{needle.lower()}%"
        phone_term = needle
        try:
            phone_term = normalize_moroccan_mobile(needle)
        except InvalidMoroccanPhone:
            phone_term = needle
        stmt = stmt.where(
            or_(
                func.lower(Order.full_name).like(pattern),
                func.lower(Order.public_reference).like(pattern),
                Order.phone_e164.like(f"%{phone_term}%"),
                Order.phone_e164.like(f"%{needle}%"),
            )
        )
    return stmt


def serialize_item(item: OrderItem) -> dict[str, object]:
    return {
        "product_slug": item.product_slug,
        "sku": item.sku_snapshot,
        "name_ar": item.name_snapshot_ar,
        "offer_code": item.offer_code,
        "offer_quantity": item.offer_quantity,
        "quantity": item.quantity,
        "unit_minor": item.unit_minor,
        "line_total_minor": item.line_total_minor,
        "saving_minor": item.saving_minor,
        "role": item.role,
    }


def serialize_history(entry: OrderStatusHistory) -> dict[str, object]:
    return {
        "from_status": entry.from_status.value if entry.from_status else None,
        "to_status": entry.to_status.value,
        "reason_code": entry.reason_code,
        "actor_type": entry.actor_type,
        "occurred_at": entry.occurred_at.isoformat() if entry.occurred_at else None,
    }


def serialize_order(order: Order, *, detail: bool) -> dict[str, object]:
    history = list(order.status_history)
    payload: dict[str, object] = {
        "public_reference": order.public_reference,
        "status": order.status.value,
        "created_at": order.created_at.isoformat() if order.created_at else None,
        "full_name": order.full_name,
        "phone_e164": order.phone_e164,
        "city": _city(history),
        "currency": order.currency,
        "subtotal_minor": order.subtotal_minor,
        "discount_minor": order.discount_minor,
        "shipping_minor": order.shipping_minor,
        "tax_minor": order.tax_minor,
        "total_minor": order.total_minor,
        "total_is_final": order.total_is_final,
        "offer_code": order.offer_code,
        "sandbox": _sandbox_flag(history),
        "item_count": len(order.items),
    }
    if detail:
        payload["items"] = [serialize_item(item) for item in order.items]
        payload["status_history"] = [serialize_history(entry) for entry in history]
        payload["status_readonly"] = True
        payload["status_readonly_reason_ar"] = (
            "تغيير الحالة غير متاح من هذه اللوحة. لا يوجد مسار مشغّل معتمد "
            "لتأكيد أو إلغاء الطلب عبر واجهة عامة، والتأكيد يتطلب إجماليًا نهائيًا."
        )
        payload["confirmation_note_ar"] = (
            "قد تتصل حنين لتأكيد الطلب. الطلب معلّق للمراجعة التشغيلية "
            "والدفع عند الاستلام."
        )
        payload["payment_label_ar"] = "الدفع عند الاستلام"
    return payload


def list_orders(
    db: Session,
    *,
    from_value: str | None,
    to_value: str | None,
    status: str | None,
    search: str | None,
    page: int,
    page_size: int,
) -> dict[str, object]:
    page = max(page, 1)
    page_size = min(max(page_size, 1), 100)
    start = end = None
    if from_value or to_value:
        start, end, _, _ = casablanca_range(from_value, to_value)
    total = db.scalar(
        _apply_filters(
            select(func.count(Order.id)),
            status=status,
            search=search,
            start=start,
            end=end,
        )
    ) or 0
    rows = db.scalars(
        _apply_filters(
            select(Order).options(
                selectinload(Order.items), selectinload(Order.status_history)
            ),
            status=status,
            search=search,
            start=start,
            end=end,
        )
        .order_by(Order.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return {
        "page": page,
        "page_size": page_size,
        "total": total,
        "orders": [serialize_order(order, detail=False) for order in rows],
    }


def get_order(db: Session, reference: str) -> dict[str, object] | None:
    order = db.scalar(
        select(Order)
        .options(selectinload(Order.items), selectinload(Order.status_history))
        .where(Order.public_reference == reference)
    )
    if order is None:
        return None
    return serialize_order(order, detail=True)
