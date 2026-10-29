from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.integrations.geoip.lookup import detectors_configured
from app.models.analytics import AnalyticsEvent
from app.models.order import Order, OrderStatus, OrderStatusHistory
from app.config import Settings

CASABLANCA = ZoneInfo("Africa/Casablanca")
MAX_RANGE_DAYS = 90
STATUS_VALUES = [status.value for status in OrderStatus]


def casablanca_range(
    from_value: str | None, to_value: str | None
) -> tuple[datetime, datetime, date, date]:
    today = datetime.now(CASABLANCA).date()
    start_day = date.fromisoformat(from_value) if from_value else today - timedelta(days=6)
    end_day = date.fromisoformat(to_value) if to_value else today
    if end_day < start_day:
        start_day, end_day = end_day, start_day
    if (end_day - start_day).days > MAX_RANGE_DAYS:
        start_day = end_day - timedelta(days=MAX_RANGE_DAYS)
    start = datetime.combine(start_day, time.min, tzinfo=CASABLANCA).astimezone(timezone.utc)
    end = datetime.combine(end_day + timedelta(days=1), time.min, tzinfo=CASABLANCA).astimezone(
        timezone.utc
    )
    return start, end, start_day, end_day


def _is_sandbox_order(order: Order) -> bool:
    for entry in order.status_history:
        metadata = entry.safe_metadata or {}
        if metadata.get("sandbox") is True:
            return True
    return False


def _city_for_order(order: Order) -> str | None:
    for entry in order.status_history:
        metadata = entry.safe_metadata or {}
        city = metadata.get("city")
        if isinstance(city, str) and city.strip():
            return city.strip()
    return None


def collect_metrics(
    db: Session,
    settings: Settings,
    *,
    from_value: str | None,
    to_value: str | None,
) -> dict[str, object]:
    start, end, start_day, end_day = casablanca_range(from_value, to_value)
    geo_ready = detectors_configured(settings)

    visits = db.scalar(
        select(func.count()).where(
            AnalyticsEvent.accepted.is_(True),
            AnalyticsEvent.created_at >= start,
            AnalyticsEvent.created_at < end,
        )
    ) or 0
    unique_visitors = db.scalar(
        select(func.count(func.distinct(AnalyticsEvent.visitor_hash))).where(
            AnalyticsEvent.accepted.is_(True),
            AnalyticsEvent.created_at >= start,
            AnalyticsEvent.created_at < end,
        )
    ) or 0

    orders = db.scalars(
        select(Order)
        .options(selectinload(Order.status_history))
        .where(Order.created_at >= start, Order.created_at < end)
    ).all()
    counted = [order for order in orders if not _is_sandbox_order(order)]
    order_count = len(counted)
    conversion_rate = (order_count / unique_visitors) if unique_visitors else 0.0

    by_status: dict[str, int] = {value: 0 for value in STATUS_VALUES}
    for order in counted:
        by_status[order.status.value] = by_status.get(order.status.value, 0) + 1

    merchandise_sum = sum(order.total_minor for order in counted)
    aov_minor = (merchandise_sum // order_count) if order_count else 0

    funnel = {
        "pending": by_status.get("pending", 0),
        "confirmed": by_status.get("confirmed", 0),
        "cancelled": by_status.get("cancelled", 0),
        "processing": by_status.get("processing", 0),
        "shipped": by_status.get("shipped", 0),
        "out_for_delivery": by_status.get("out_for_delivery", 0),
        "delivered": by_status.get("delivered", 0),
        "returned": by_status.get("returned", 0),
        "note_ar": (
            "لا توجد حالة مستقلة «بانتظار التأكيد الهاتفي» — الطلبات الجديدة تُحفظ "
            "كمعلّقة (pending) وقد تتصل حنين لتأكيدها. التأكيد التشغيلي غير متاح "
            "من هذه اللوحة لأن الإجمالي غير نهائي."
        ),
    }

    path_rows = db.execute(
        select(AnalyticsEvent.path, func.count())
        .where(
            AnalyticsEvent.accepted.is_(True),
            AnalyticsEvent.created_at >= start,
            AnalyticsEvent.created_at < end,
        )
        .group_by(AnalyticsEvent.path)
        .order_by(func.count().desc())
        .limit(20)
    ).all()

    city_counts: dict[str, int] = defaultdict(int)
    missing_city = 0
    for order in counted:
        city = _city_for_order(order)
        if city:
            city_counts[city] += 1
        else:
            missing_city += 1
    orders_by_city = [
        {"city": city, "orders": count}
        for city, count in sorted(city_counts.items(), key=lambda item: (-item[1], item[0]))
    ]
    if missing_city:
        orders_by_city.append({"city": None, "orders": missing_city})

    series_days = []
    cursor = start_day
    while cursor <= end_day:
        series_days.append(cursor)
        cursor += timedelta(days=1)

    visit_by_day: dict[str, int] = {day.isoformat(): 0 for day in series_days}
    accepted_events = db.scalars(
        select(AnalyticsEvent).where(
            AnalyticsEvent.accepted.is_(True),
            AnalyticsEvent.created_at >= start,
            AnalyticsEvent.created_at < end,
        )
    ).all()
    for event in accepted_events:
        occurred = event.created_at
        if occurred.tzinfo is None:
            occurred = occurred.replace(tzinfo=timezone.utc)
        key = occurred.astimezone(CASABLANCA).date().isoformat()
        if key in visit_by_day:
            visit_by_day[key] += 1

    orders_by_day: dict[str, int] = {day.isoformat(): 0 for day in series_days}
    for order in counted:
        occurred = order.created_at
        if occurred.tzinfo is None:
            occurred = occurred.replace(tzinfo=timezone.utc)
        key = occurred.astimezone(CASABLANCA).date().isoformat()
        if key in orders_by_day:
            orders_by_day[key] += 1

    return {
        "timezone": "Africa/Casablanca",
        "from": start_day.isoformat(),
        "to": end_day.isoformat(),
        "geo_detectors_configured": geo_ready,
        "banner_ar": None
        if geo_ready
        else (
            "كشف الدولة/VPN غير مُعد — المقاييس تستثني الزيارات غير المحققة"
        ),
        "visits": visits,
        "unique_visitors": unique_visitors,
        "orders": order_count,
        "conversion_rate": conversion_rate,
        "conversion_basis": "unique_visitors",
        "conversion_label_ar": "نسبة التحويل = الطلبات ÷ الزائرات الفريدات",
        "orders_by_status": by_status,
        "merchandise_total_minor": merchandise_sum,
        "aov_minor": aov_minor,
        "aov_label_ar": "قيمة المنتجات",
        "total_is_final": False,
        "cod_funnel": funnel,
        "traffic_by_path": [
            {"path": path, "visits": count} for path, count in path_rows
        ],
        "orders_by_city": orders_by_city,
        "series": [
            {
                "date": day.isoformat(),
                "visits": visit_by_day[day.isoformat()],
                "orders": orders_by_day[day.isoformat()],
            }
            for day in series_days
        ],
    }
