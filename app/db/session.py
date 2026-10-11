from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings


def _normalize_database_url(url: str) -> str:
    """Pin bare PostgreSQL URLs to the psycopg (v3) driver.

    SQLAlchemy defaults the ``postgresql://`` / ``postgres://`` schemes to the
    legacy ``psycopg2`` dialect, which is not installed (the project depends on
    ``psycopg[binary]`` v3). If the deployment supplies a bare scheme we rewrite
    it to ``postgresql+psycopg://`` so the correct, installed driver is used.
    URLs that already name a driver (e.g. ``postgresql+psycopg://``) and
    non-PostgreSQL URLs (e.g. ``sqlite+pysqlite://``) are left untouched.
    """
    for bare_scheme in ("postgresql://", "postgres://"):
        if url.startswith(bare_scheme):
            return "postgresql+psycopg://" + url[len(bare_scheme) :]
    return url


settings = get_settings()
engine = create_engine(_normalize_database_url(settings.database_url), pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
