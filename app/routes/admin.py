from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.session import get_db
from app.errors import DomainProblem
from app.schemas.admin import AdminLoginRequest
from app.services.admin_auth import (
    COOKIE_NAME,
    clear_session_cookie,
    create_session,
    raise_if_admin_disabled,
    require_admin,
    revoke_session,
    set_session_cookie,
    verify_credentials,
)
from app.services.admin_metrics import collect_metrics
from app.services.admin_orders import get_order, list_orders

router = APIRouter(prefix="/v1/admin", tags=["admin"])


def _admin_session(request: Request, db: Session = Depends(get_db)):
    return require_admin(request, db)


@router.post("/login")
def login(
    payload: AdminLoginRequest,
    response: Response,
    db: Session = Depends(get_db),
) -> dict[str, str]:
    settings = get_settings()
    raise_if_admin_disabled(settings)
    if not verify_credentials(payload.username, payload.password, settings):
        raise DomainProblem(
            401,
            "ADMIN_UNAUTHORIZED",
            "بيانات الدخول غير صحيحة",
            "تعذر تسجيل الدخول.",
        )
    token = create_session(db, settings.admin_username_value or payload.username, settings)
    set_session_cookie(response, token, settings)
    response.headers["Cache-Control"] = "no-store"
    return {"status": "ok"}


@router.post("/logout")
def logout(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> dict[str, str]:
    revoke_session(db, request.cookies.get(COOKIE_NAME))
    clear_session_cookie(response)
    response.headers["Cache-Control"] = "no-store"
    return {"status": "ok"}


@router.get("/me")
def me(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    session = require_admin(request, db)
    response.headers["Cache-Control"] = "no-store, private"
    return {
        "username": session.username,
        "expires_at": session.expires_at.isoformat() if session.expires_at else None,
    }


@router.get("/metrics")
def metrics(
    response: Response,
    db: Session = Depends(get_db),
    _session=Depends(_admin_session),
    from_date: Annotated[str | None, Query(alias="from")] = None,
    to_date: Annotated[str | None, Query(alias="to")] = None,
) -> dict[str, object]:
    try:
        payload = collect_metrics(
            db, get_settings(), from_value=from_date, to_value=to_date
        )
    except ValueError as exc:
        raise DomainProblem(
            422,
            "VALIDATION_FAILED",
            "تعذر التحقق من البيانات",
            "صيغة التاريخ غير صالحة. استخدمي YYYY-MM-DD.",
        ) from exc
    response.headers["Cache-Control"] = "no-store, private"
    return payload


@router.get("/orders")
def orders(
    response: Response,
    db: Session = Depends(get_db),
    _session=Depends(_admin_session),
    from_date: Annotated[str | None, Query(alias="from")] = None,
    to_date: Annotated[str | None, Query(alias="to")] = None,
    status: Annotated[str | None, Query()] = None,
    search: Annotated[str | None, Query(max_length=120)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> dict[str, object]:
    try:
        payload = list_orders(
            db,
            from_value=from_date,
            to_value=to_date,
            status=status,
            search=search,
            page=page,
            page_size=page_size,
        )
    except ValueError as exc:
        raise DomainProblem(
            422,
            "VALIDATION_FAILED",
            "تعذر التحقق من البيانات",
            "صيغة التاريخ غير صالحة. استخدمي YYYY-MM-DD.",
        ) from exc
    response.headers["Cache-Control"] = "no-store, private"
    return payload


@router.get("/orders/{reference}")
def order_detail(
    reference: str,
    response: Response,
    db: Session = Depends(get_db),
    _session=Depends(_admin_session),
) -> dict[str, object]:
    payload = get_order(db, reference)
    if payload is None:
        raise DomainProblem(
            404,
            "ORDER_NOT_FOUND",
            "الطلب غير موجود",
            "تعذر العثور على مرجع الطلب.",
        )
    response.headers["Cache-Control"] = "no-store, private"
    return payload
