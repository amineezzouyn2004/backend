from __future__ import annotations

import re
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.config import Settings
from app.integrations.geoip.lookup import (
    classify_request,
    is_accepted_morocco,
    reject_reason,
)
from app.models.analytics import AnalyticsEvent
from app.services.admin_auth import hash_ip, hash_visitor

_PATH_RE = re.compile(r"^/[A-Za-z0-9._~\-/]{0,499}$")
_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_BOT_UA_RE = re.compile(
    r"bot|crawler|spider|curl|wget|python-requests|httpclient",
    re.IGNORECASE,
)


def normalize_path(raw: str | None) -> str | None:
    if not raw:
        return None
    path = raw.strip().split("?", 1)[0].split("#", 1)[0]
    if not path.startswith("/"):
        path = "/" + path
    if len(path) > 500 or not _PATH_RE.fullmatch(path):
        return None
    return path


def normalize_slug(raw: str | None) -> str | None:
    if not raw:
        return None
    slug = raw.strip().lower()
    if not slug or len(slug) > 160 or not _SLUG_RE.fullmatch(slug):
        return None
    return slug


def is_ingest_bot(method: str, user_agent: str | None) -> bool:
    if method.upper() != "POST":
        return True
    ua = (user_agent or "").strip()
    if not ua or ua == "-":
        return True
    if _BOT_UA_RE.search(ua):
        return True
    return False


def ingest_pageview(
    db: Session,
    settings: Settings,
    *,
    request,
    path: str | None,
    product_slug: str | None,
    user_agent: str | None,
    method: str,
) -> None:
    if is_ingest_bot(method, user_agent):
        return
    normalized_path = normalize_path(path)
    if normalized_path is None:
        return
    ip, classification = classify_request(request, settings)
    if ip is None:
        event = AnalyticsEvent(
            created_at=datetime.now(timezone.utc),
            path=normalized_path,
            product_slug=normalize_slug(product_slug),
            visitor_hash=hash_visitor(settings, "unknown", user_agent or ""),
            ip_hash=hash_ip(settings, "unknown"),
            country=classification.country,
            vpn_flag=classification.is_vpn,
            proxy_flag=classification.is_proxy,
            anonymous_flag=classification.is_anonymous,
            hosting_flag=classification.is_hosting,
            accepted=False,
            source="first_party",
            reject_reason="no_ip",
        )
        db.add(event)
        db.commit()
        return
    accepted = is_accepted_morocco(classification)
    event = AnalyticsEvent(
        created_at=datetime.now(timezone.utc),
        path=normalized_path,
        product_slug=normalize_slug(product_slug),
        visitor_hash=hash_visitor(settings, ip, user_agent or ""),
        ip_hash=hash_ip(settings, ip),
        country=classification.country,
        vpn_flag=classification.is_vpn,
        proxy_flag=classification.is_proxy,
        anonymous_flag=classification.is_anonymous,
        hosting_flag=classification.is_hosting,
        accepted=accepted,
        source="first_party",
        reject_reason=None if accepted else reject_reason(classification),
    )
    db.add(event)
    db.commit()
