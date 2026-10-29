"""Morocco + VPN/proxy classification for admin metrics.

Primary: MaxMind GeoIP2 (local MMDB or Country/Insights web). This uses the
same Account ID / license key as minFraud but MUST NOT call minFraud Score.
Insights here is GeoIP Insights, not minFraud Insights.

Second signal already arriving at the proxy: Cloudflare ``CF-IPCountry`` when
the immediate peer is in ``TRUSTED_PROXY_IPS``. That header is country only —
there is no second VPN/proxy API (ipinfo, proxycheck, IPQS, …) in this repo.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from app.config import Settings
from app.integrations.minfraud.ip import client_ip_for_minfraud

logger = logging.getLogger("hanin.geoip")

MOROCCO = "MA"


class _ClientPeer(Protocol):
    host: str | None


class _HeadersLike(Protocol):
    def get(self, key: str) -> str | None: ...


class _RequestLike(Protocol):
    client: _ClientPeer | None
    headers: _HeadersLike


@dataclass(frozen=True)
class IpClassification:
    country: str | None
    is_vpn: bool | None
    is_proxy: bool | None
    is_anonymous: bool | None
    is_hosting: bool | None
    country_source: str | None
    vpn_source: str | None

    @property
    def verified(self) -> bool:
        return (
            self.country is not None
            and self.is_vpn is not None
            and self.is_proxy is not None
            and self.is_anonymous is not None
            and self.is_hosting is not None
        )


def is_accepted_morocco(classification: IpClassification) -> bool:
    if not classification.verified:
        return False
    if (classification.country or "").upper() != MOROCCO:
        return False
    if classification.is_vpn or classification.is_proxy:
        return False
    if classification.is_anonymous or classification.is_hosting:
        return False
    return True


def reject_reason(classification: IpClassification) -> str:
    if not classification.verified:
        return "unverified"
    if (classification.country or "").upper() != MOROCCO:
        return "non_ma"
    if classification.is_vpn:
        return "vpn"
    if classification.is_proxy:
        return "proxy"
    if classification.is_anonymous:
        return "anonymous"
    if classification.is_hosting:
        return "hosting"
    return "rejected"


def detectors_configured(settings: Settings) -> bool:
    """True only when both country and VPN/anonymous detectors can run."""
    country_ok = bool(settings.geolite_country_db_path) or _web_geo_ready(settings)
    vpn_ok = bool(settings.anonymous_ip_db_path) or (
        _web_geo_ready(settings) and settings.maxmind_geoip_service == "insights"
    )
    return country_ok and vpn_ok


def _web_geo_ready(settings: Settings) -> bool:
    return (
        settings.maxmind_geoip_enabled
        and settings.maxmind_account_id_int is not None
        and settings.maxmind_license_key_value is not None
    )


def cloudflare_country(
    request: _RequestLike, trusted_proxy_ips: list[str]
) -> str | None:
    """Country from CF-IPCountry only when the immediate peer is a trusted proxy.

    Not a VPN detector. ``XX`` / ``T1`` are treated as unknown.
    """
    trusted = {item.strip() for item in trusted_proxy_ips if item.strip()}
    peer = request.client.host if request.client else None
    if not peer or peer not in trusted:
        return None
    value = (
        request.headers.get("cf-ipcountry")
        or request.headers.get("CF-IPCountry")
        or request.headers.get("Cf-Ipcountry")
    )
    if not value:
        return None
    code = value.strip().upper()
    if len(code) != 2 or code in {"XX", "T1"}:
        return None
    return code


def _anonymizer_flags(payload: Any) -> tuple[bool, bool, bool, bool]:
    is_vpn = bool(getattr(payload, "is_anonymous_vpn", False))
    is_proxy = bool(
        getattr(payload, "is_public_proxy", False)
        or getattr(payload, "is_residential_proxy", False)
        or getattr(payload, "is_tor_exit_node", False)
    )
    is_anonymous = bool(getattr(payload, "is_anonymous", False))
    is_hosting = bool(getattr(payload, "is_hosting_provider", False))
    return is_vpn, is_proxy, is_anonymous, is_hosting


def _lookup_local_country(path: str, ip: str) -> str | None:
    try:
        from geoip2.database import Reader
    except ImportError:
        logger.warning("geoip2_database_unavailable")
        return None
    try:
        with Reader(path) as reader:
            response = reader.country(ip)
    except Exception:  # noqa: BLE001 — ingest must never raise to the storefront
        logger.warning("geoip_country_db_failed")
        return None
    code = getattr(getattr(response, "country", None), "iso_code", None)
    return str(code).upper() if code else None


def _lookup_local_anonymous(path: str, ip: str) -> tuple[bool, bool, bool, bool] | None:
    try:
        from geoip2.database import Reader
    except ImportError:
        logger.warning("geoip2_database_unavailable")
        return None
    try:
        with Reader(path) as reader:
            response = reader.anonymous_ip(ip)
    except Exception:  # noqa: BLE001
        logger.warning("geoip_anonymous_db_failed")
        return None
    return _anonymizer_flags(response)


def _lookup_web(settings: Settings, ip: str) -> tuple[str | None, tuple[bool, bool, bool, bool] | None]:
    try:
        from geoip2.webservice import Client
    except ImportError:
        logger.warning("geoip2_webservice_unavailable")
        return None, None
    account_id = settings.maxmind_account_id_int
    license_key = settings.maxmind_license_key_value
    if account_id is None or license_key is None:
        return None, None
    try:
        client = Client(
            account_id,
            license_key,
            timeout=settings.maxmind_geoip_timeout_seconds,
        )
        try:
            if settings.maxmind_geoip_service == "insights":
                response = client.insights(ip)
                country = getattr(getattr(response, "country", None), "iso_code", None)
                anonymizer = getattr(response, "anonymizer", None) or getattr(
                    response, "traits", None
                )
                flags = _anonymizer_flags(anonymizer) if anonymizer is not None else None
                return (str(country).upper() if country else None), flags
            response = client.country(ip)
            country = getattr(getattr(response, "country", None), "iso_code", None)
            return (str(country).upper() if country else None), None
        finally:
            close = getattr(client, "close", None)
            if callable(close):
                close()
    except Exception:  # noqa: BLE001
        logger.warning("geoip_web_lookup_failed")
        return None, None


def classify_ip(ip: str | None, settings: Settings, cf_country: str | None) -> IpClassification:
    country: str | None = None
    country_source: str | None = None
    flags: tuple[bool, bool, bool, bool] | None = None
    vpn_source: str | None = None

    if ip:
        country_db = settings.geolite_country_db_path
        if country_db and Path(country_db).is_file():
            country = _lookup_local_country(country_db, ip)
            if country:
                country_source = "maxmind_country_db"
        anon_db = settings.anonymous_ip_db_path
        if anon_db and Path(anon_db).is_file():
            flags = _lookup_local_anonymous(anon_db, ip)
            if flags is not None:
                vpn_source = "maxmind_anonymous_ip_db"
        if (country is None or flags is None) and _web_geo_ready(settings):
            web_country, web_flags = _lookup_web(settings, ip)
            if country is None and web_country:
                country = web_country
                country_source = (
                    "maxmind_geoip_insights"
                    if settings.maxmind_geoip_service == "insights"
                    else "maxmind_geoip_country"
                )
            if flags is None and web_flags is not None:
                flags = web_flags
                vpn_source = "maxmind_geoip_insights"

    if cf_country:
        if country is None:
            country = cf_country
            country_source = "cloudflare_cf_ipcountry"
        elif country != cf_country:
            # Disagreeing country signals: do not accept as Morocco.
            country_source = f"{country_source}+cloudflare_conflict"
            if country != MOROCCO or cf_country != MOROCCO:
                country = country if country != MOROCCO else cf_country

    is_vpn = flags[0] if flags else None
    is_proxy = flags[1] if flags else None
    is_anonymous = flags[2] if flags else None
    is_hosting = flags[3] if flags else None
    return IpClassification(
        country=country,
        is_vpn=is_vpn,
        is_proxy=is_proxy,
        is_anonymous=is_anonymous,
        is_hosting=is_hosting,
        country_source=country_source,
        vpn_source=vpn_source,
    )


def classify_request(request: _RequestLike, settings: Settings) -> tuple[str | None, IpClassification]:
    ip = client_ip_for_minfraud(request, settings.trusted_proxy_ip_list)
    cf_country = cloudflare_country(request, settings.trusted_proxy_ip_list)
    return ip, classify_ip(ip, settings, cf_country)
