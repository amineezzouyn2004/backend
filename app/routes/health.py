from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.errors import DomainProblem


router = APIRouter(tags=["health"])


@router.get("/health/live")
def live() -> dict[str, str]:
    return {"status": "live"}


@router.get("/health/ready")
def ready(db: Session = Depends(get_db)) -> dict[str, str]:
    try:
        db.execute(text("SELECT 1"))
        db.execute(text("SELECT version_num FROM alembic_version LIMIT 1"))
    except SQLAlchemyError as exc:
        raise DomainProblem(
            status=503,
            code="NOT_READY",
            title="الخدمة غير جاهزة",
            detail="قاعدة البيانات أو مخططها غير جاهز.",
        ) from exc
    return {"status": "ready"}
