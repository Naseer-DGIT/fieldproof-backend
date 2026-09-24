"""Security headers for FieldProof.

Two behaviors, both gated on the environment:

1. HTTPS redirect — if a request arrives over plain HTTP and the
   environment is staging or prod, respond with 307 to the same URL
   over HTTPS.

2. HSTS — on every response in staging or prod, send
   `Strict-Transport-Security: max-age=31536000; includeSubDomains`.
   The browser refuses plain HTTP for the next year.

In dev and lab, neither is active: tests and local tooling use HTTP.

Real TLS termination is the load balancer's job (S15). This module
only tells clients to use HTTPS.
"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import RedirectResponse, Response

from app.core.config import settings


class HttpsRedirectMiddleware(BaseHTTPMiddleware):
    """Redirect plain HTTP to HTTPS when `settings.force_https`.

    Respects `X-Forwarded-Proto` so it works behind a proxy that
    terminates TLS. Never redirects `/health` — probes run over HTTP
    inside the private network.
    """

    async def dispatch(self, request: Request, call_next):
        if not settings.force_https:
            return await call_next(request)

        if request.url.path == "/health":
            return await call_next(request)

        proto = request.headers.get("x-forwarded-proto", request.url.scheme)
        if proto == "https":
            return await call_next(request)

        https_url = request.url.replace(scheme="https")
        return RedirectResponse(url=str(https_url), status_code=307)


class HstsHeaderMiddleware(BaseHTTPMiddleware):
    """Add HSTS to every response when `settings.hsts_enabled`."""

    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        if settings.hsts_enabled:
            response.headers["Strict-Transport-Security"] = (
                f"max-age={settings.hsts_max_age}; includeSubDomains"
            )
        return response
