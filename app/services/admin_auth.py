from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import Request, Response
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.errors import DomainProblem
from app.models.admin import AdminSession

logger = logging.getLogger("hanin.admin")

COOKIE_NAME = "hanin_admin"
COOKIE_PATH = "/v1/admin"


def _sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def hmac_hex(secret: str, value: str) -> str:
    return hmac.new(secret.encode("utf-8"), value.encode("utf-8"), hashlib.sha256).hexdigest()


def ip_hash_secret(settings: Settings) -> str:
    return settings.ip_hash_secret_value or "hanin-unconfigured-ip-hash"


def hash_ip(settings: Settings, ip: str) -> str:
    return hmac_hex(ip_hash_secret(settings), ip)


def hash_visitor(settings: Settings, ip: str, user_agent: str) -> str:
    return hmac_hex(ip_hash_secret(settings), f"{ip}\n{user_agent}")


def _clean_secret(value: str) -> str:
    return value.replace("\ufeff", "").strip()


def _safe_equal(left: str, right: str) -> bool:
    left_b = left.encode("utf-8")
    right_b = right.encode("utf-8")
    if len(left_b) != len(right_b):
        return False
    return hmac.compare_digest(left_b, right_b)


def verify_credentials(username: str, password: str, settings: Settings) -> bool:
    expected_user = settings.admin_username_value
    if expected_user is None:
        return False
    got_user = _clean_secret(username)
    got_password = _clean_secret(password)
    if not got_user or not got_password:
        return False
    if not _safe_equal(got_user, expected_user):
        return False
    password_hash = settings.admin_password_hash_value
    if password_hash:
        digest = _sha256_hex(got_password)
        return _safe_equal(digest, password_hash)
    expected_password = settings.admin_password_value
    if not expected_password:
        return False
    return _safe_equal(got_password, expected_password)


def raise_if_admin_disabled(settings: Settings | None = None) -> None:
    cfg = settings or get_settings()
    if not cfg.admin_is_configured():
        raise DomainProblem(
            503,
            "ADMIN_DISABLED",
            "لوحة الإدارة غير مهيأة",
            "تعذر فتح لوحة الإدارة لأن بيانات الدخول غير مضبوطة.",
        )


def _exception_blob(exc: BaseException) -> str:
    chunks = [str(exc)]
    current: BaseException | None = exc
    for _ in range(5):
        current = current.__cause__ or current.__context__
        if current is None:
            break
        chunks.append(str(current))
    return " ".join(chunks).lower()


def reraise_if_admin_sessions_missing(exc: BaseException) -> None:
    blob = _exception_blob(exc)
    missing = (
        "no such table" in blob
        or "does not exist" in blob
        or "undefinedtable" in blob
    )
    if "admin_sessions" not in blob or not missing:
        return
    logger.warning("admin_sessions_table_missing")
    raise DomainProblem(
        503,
        "ADMIN_SESSIONS_UNAVAILABLE",
        "جدول الجلسات غير جاهز",
        "جدول الجلسات غير جاهز.",
    ) from exc


def create_session(db: Session, username: str, settings: Settings) -> str:
    token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    session = AdminSession(
        token_hash=_sha256_hex(token),
        username=username.strip(),
        created_at=now,
        expires_at=now + timedelta(hours=settings.admin_session_hours),
    )
    db.add(session)
    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        reraise_if_admin_sessions_missing(exc)
        raise
    logger.info("admin_session_created")
    return token


def revoke_session(db: Session, token: str | None) -> None:
    if not token:
        return
    try:
        session = db.scalar(
            select(AdminSession).where(AdminSession.token_hash == _sha256_hex(token))
        )
        if session is None or session.revoked_at is not None:
            return
        session.revoked_at = datetime.now(timezone.utc)
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        reraise_if_admin_sessions_missing(exc)
        raise
    logger.info("admin_session_revoked")


def load_session(db: Session, token: str | None) -> AdminSession | None:
    if not token:
        return None
    try:
        session = db.scalar(
            select(AdminSession).where(AdminSession.token_hash == _sha256_hex(token))
        )
    except SQLAlchemyError as exc:
        reraise_if_admin_sessions_missing(exc)
        raise
    if session is None or session.revoked_at is not None:
        return None
    now = datetime.now(timezone.utc)
    expires = session.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires <= now:
        return None
    return session


def cookie_flags(settings: Settings) -> tuple[bool, Literal["lax", "none"]]:
    """Host-only cookie. Do not set Domain — JS must never read the token.

    Production admin fetch is same-origin via the hanin.cc /v1 Next rewrite,
    so SameSite=Lax is enough. Secure is required on HTTPS. Path=/v1/admin
    covers login, me, metrics, orders, and logout.
    """
    if settings.environment.strip().lower() == "production":
        return True, "lax"
    return False, "lax"


def set_session_cookie(response: Response, token: str, settings: Settings) -> None:
    secure, samesite = cookie_flags(settings)
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        secure=secure,
        samesite=samesite,
        path=COOKIE_PATH,
        max_age=settings.admin_session_hours * 3600,
    )


def clear_session_cookie(response: Response, settings: Settings | None = None) -> None:
    cfg = settings or get_settings()
    secure, samesite = cookie_flags(cfg)
    response.delete_cookie(
        key=COOKIE_NAME,
        path=COOKIE_PATH,
        secure=secure,
        httponly=True,
        samesite=samesite,
    )


def require_admin(request: Request, db: Session) -> AdminSession:
    settings = get_settings()
    raise_if_admin_disabled(settings)
    token = request.cookies.get(COOKIE_NAME)
    session = load_session(db, token)
    if session is None:
        raise DomainProblem(
            401,
            "ADMIN_UNAUTHORIZED",
            "غير مصرّح",
            "انتهت الجلسة أو غير صالحة. يرجى تسجيل الدخول.",
        )
    return session
