from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.config import get_settings
from app.errors import (
    DomainProblem,
    domain_problem_handler,
    validation_problem_handler,
)
from app.middleware import RequestContextMiddleware, RequestGuardMiddleware
from app.routes import catalog, health, offers, orders


settings = get_settings()
openapi_url = "/openapi.json" if settings.openapi_enabled else None
docs_url = "/docs" if settings.openapi_enabled else None

app = FastAPI(
    title="Hanin API",
    version="0.1.0",
    description=(
        "Foundation API. Orders remain pending because address, shipping, tax, "
        "and operational confirmation are TODO — INFORMATION REQUIRED."
    ),
    openapi_url=openapi_url,
    docs_url=docs_url,
    redoc_url=None,
)
app.add_exception_handler(DomainProblem, domain_problem_handler)
app.add_exception_handler(RequestValidationError, validation_problem_handler)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Idempotency-Key", "X-Request-ID"],
)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.trusted_host_list)
app.add_middleware(RequestGuardMiddleware, settings=settings)
app.add_middleware(RequestContextMiddleware)
app.include_router(health.router)
app.include_router(catalog.router)
app.include_router(offers.router)
app.include_router(orders.router)
