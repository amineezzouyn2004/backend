import time
import uuid
from collections import defaultdict, deque
from collections.abc import Awaitable, Callable

from fastapi import Request
from fastapi.responses import JSONResponse, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import Settings


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        supplied = request.headers.get("X-Request-ID", "")
        correlation_id = supplied if 0 < len(supplied) <= 100 else str(uuid.uuid4())
        request.state.correlation_id = correlation_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = correlation_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Content-Security-Policy"] = "frame-ancestors 'none'; base-uri 'none'"
        return response


class RequestGuardMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: object, settings: Settings):
        super().__init__(app)
        self.settings = settings
        self._requests: dict[str, deque[float]] = defaultdict(deque)

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        content_length = request.headers.get("content-length")
        try:
            request_size = int(content_length) if content_length else 0
        except ValueError:
            request_size = self.settings.max_request_body_bytes + 1
        if request_size > self.settings.max_request_body_bytes:
            return JSONResponse(
                {
                    "type": "https://api.hanin.cc/problems/request-too-large",
                    "title": "الطلب كبير جدًا",
                    "status": 413,
                    "code": "REQUEST_TOO_LARGE",
                    "detail": "حجم البيانات المرسلة يتجاوز الحد المسموح.",
                    "correlation_id": getattr(request.state, "correlation_id", None),
                },
                status_code=413,
                media_type="application/problem+json",
            )
        origin = request.headers.get("origin")
        origin_protected = {
            "/v1/orders",
            "/v1/admin/login",
            "/v1/events/view",
        }
        if (
            request.method == "POST"
            and request.url.path in origin_protected
            and origin
            and origin not in self.settings.cors_origin_list
        ):
            return JSONResponse(
                {
                    "type": "https://api.hanin.cc/problems/origin-not-allowed",
                    "title": "المصدر غير مسموح",
                    "status": 403,
                    "code": "ORIGIN_NOT_ALLOWED",
                    "detail": "تعذر قبول الطلب من هذا المصدر.",
                    "correlation_id": getattr(request.state, "correlation_id", None),
                },
                status_code=403,
                media_type="application/problem+json",
            )
        if request.method == "POST" and request.url.path == "/v1/admin/login":
            limited = self._hit_limit(
                f"admin-login:{request.client.host if request.client else 'unknown'}",
                self.settings.admin_login_rate_limit_per_minute,
            )
            if limited:
                return self._rate_limited(request)
        if request.method == "POST" and request.url.path == "/v1/events/view":
            limited = self._hit_limit(
                f"events:{request.client.host if request.client else 'unknown'}",
                self.settings.event_rate_limit_per_minute,
            )
            if limited:
                # Do not surface errors to the storefront beacon.
                return Response(status_code=204)
        if (
            self.settings.rate_limit_enabled
            and request.method == "POST"
            and request.url.path == "/v1/orders"
        ):
            client = request.client.host if request.client else "unknown"
            if self._hit_limit(f"orders:{client}", self.settings.order_rate_limit_per_minute):
                return self._rate_limited(request)
        return await call_next(request)

    def _hit_limit(self, key: str, limit: int) -> bool:
        now = time.monotonic()
        bucket = self._requests[key]
        while bucket and bucket[0] <= now - 60:
            bucket.popleft()
        if len(bucket) >= limit:
            return True
        bucket.append(now)
        return False

    def _rate_limited(self, request: Request) -> JSONResponse:
        return JSONResponse(
            {
                "type": "https://api.hanin.cc/problems/rate-limited",
                "title": "محاولات كثيرة",
                "status": 429,
                "code": "RATE_LIMITED",
                "detail": "انتظري قليلًا ثم حاولي مجددًا.",
                "correlation_id": getattr(request.state, "correlation_id", None),
            },
            status_code=429,
            headers={"Retry-After": "60"},
            media_type="application/problem+json",
        )
