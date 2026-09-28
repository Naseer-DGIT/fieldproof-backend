"""Security headers and TLS enforcement for FieldProof.

Three behaviors, all gated on environment or always-on depending on
the header:

1. HTTPS redirect — gated on `settings.force_https`
2. HSTS — gated on `settings.hsts_enabled`
3. Baseline security headers — always on:
   - X-Content-Type-Options: nosniff
   - X-Frame-Options: DENY
   - Referrer-Policy: no-referrer
   - Content-Security-Policy: default-src 'none'

The CSP is a JSON API default: nothing should be loaded by a browser
from an API response. If a future endpoint serves HTML, that endpoint
sets its own CSP.
"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import RedirectResponse, Response

from app.core.config import settings

_DEFAULT_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
}


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add the baseline security headers to every response."""

    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        for name, value in _DEFAULT_HEADERS.items():
            response.headers.setdefault(name, value)
        return response


class HttpsRedirectMiddleware(BaseHTTPMiddleware):
    """Redirect plain HTTP to HTTPS when `settings.force_https`.

    Respects `X-Forwarded-Proto` so it works behind a proxy that
    terminates TLS. Never redirects `/health`.
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
