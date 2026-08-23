from dataclasses import dataclass
from typing import Any

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


@dataclass
class DomainProblem(Exception):
    status: int
    code: str
    title: str
    detail: str


def problem_payload(
    request: Request,
    *,
    status: int,
    code: str,
    title: str,
    detail: str,
    errors: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "type": f"https://api.hanin.cc/problems/{code.lower()}",
        "title": title,
        "status": status,
        "code": code,
        "detail": detail,
        "instance": request.url.path,
        "correlation_id": getattr(request.state, "correlation_id", None),
    }
    if errors:
        payload["errors"] = errors
    return payload


async def domain_problem_handler(request: Request, exc: DomainProblem) -> JSONResponse:
    return JSONResponse(
        problem_payload(
            request,
            status=exc.status,
            code=exc.code,
            title=exc.title,
            detail=exc.detail,
        ),
        status_code=exc.status,
        media_type="application/problem+json",
    )


async def validation_problem_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    errors = [
        {
            "field": ".".join(str(part) for part in error["loc"] if part != "body"),
            "message": "القيمة غير صالحة.",
            "type": error["type"],
        }
        for error in exc.errors()
    ]
    return JSONResponse(
        problem_payload(
            request,
            status=422,
            code="VALIDATION_FAILED",
            title="تعذر التحقق من البيانات",
            detail="راجعي الحقول المشار إليها ثم حاولي مجددًا.",
            errors=errors,
        ),
        status_code=422,
        media_type="application/problem+json",
    )
