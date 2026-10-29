from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.session import get_db
from app.schemas.events import PageViewIn
from app.services.analytics import ingest_pageview

router = APIRouter(prefix="/v1/events", tags=["events"])


@router.post("/view", status_code=204)
def record_view(
    payload: PageViewIn,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> Response:
    try:
        ingest_pageview(
            db,
            get_settings(),
            request=request,
            path=payload.path,
            product_slug=payload.product_slug,
            user_agent=request.headers.get("user-agent"),
            method=request.method,
        )
    except Exception:  # noqa: BLE001 — never break the storefront
        pass
    response.headers["Cache-Control"] = "no-store"
    return Response(status_code=204)
