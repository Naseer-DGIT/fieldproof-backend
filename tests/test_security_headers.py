"""TLS enforcement and HSTS tests.

Two kinds of test:

1. Direct middleware tests. Instantiate the middleware with a fake
   request and assert the response headers. Fast, no server.

2. Running-server tests. Assert the dev-mode behavior of the live
   backend (no HSTS, no redirect).

`Settings` is a frozen dataclass, so tests cannot mutate a field on the
singleton. They replace the whole object in the middleware module's
namespace with `dataclasses.replace`.
"""

import asyncio
import dataclasses
import os
import sys

import httpx
import pytest
from starlette.requests import Request
from starlette.responses import Response

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core import security_headers  # noqa: E402
from app.core.config import settings as real_settings  # noqa: E402

BASE = os.getenv("BASE_URL", "http://localhost:8000")


def _make_request(path: str = "/api/v1/auth/login", headers: dict | None = None):
    scope = {
        "type": "http",
        "method": "POST",
        "path": path,
        "headers": [
            (k.lower().encode(), v.encode())
            for k, v in (headers or {}).items()
        ],
        "scheme": "http",
        "query_string": b"",
        "server": ("localhost", 8000),
    }
    return Request(scope)


async def _call_next_ok(request):
    return Response("ok", status_code=200)


# --- Direct middleware tests ---

def test_hsts_header_added_when_enabled(monkeypatch):
    monkeypatch.setattr(
        security_headers,
        "settings",
        dataclasses.replace(real_settings, hsts_enabled=True),
    )

    async def noop(scope, receive, send):
        pass

    mw = security_headers.HstsHeaderMiddleware(noop)
    response = asyncio.run(mw.dispatch(_make_request(), _call_next_ok))

    assert "strict-transport-security" in response.headers
    hsts = response.headers["strict-transport-security"]
    assert "max-age=31536000" in hsts
    assert "includeSubDomains" in hsts


def test_hsts_header_absent_when_disabled(monkeypatch):
    monkeypatch.setattr(
        security_headers,
        "settings",
        dataclasses.replace(real_settings, hsts_enabled=False),
    )

    async def noop(scope, receive, send):
        pass

    mw = security_headers.HstsHeaderMiddleware(noop)
    response = asyncio.run(mw.dispatch(_make_request(), _call_next_ok))

    assert "strict-transport-security" not in response.headers


def test_redirect_when_force_https_enabled(monkeypatch):
    monkeypatch.setattr(
        security_headers,
        "settings",
        dataclasses.replace(real_settings, force_https=True),
    )

    async def noop(scope, receive, send):
        pass

    mw = security_headers.HttpsRedirectMiddleware(noop)
    response = asyncio.run(mw.dispatch(_make_request(), _call_next_ok))

    assert response.status_code == 307
    assert response.headers["location"].startswith("https://")


def test_no_redirect_when_forwarded_proto_is_https(monkeypatch):
    monkeypatch.setattr(
        security_headers,
        "settings",
        dataclasses.replace(real_settings, force_https=True),
    )

    async def noop(scope, receive, send):
        pass

    mw = security_headers.HttpsRedirectMiddleware(noop)
    req = _make_request(headers={"X-Forwarded-Proto": "https"})
    response = asyncio.run(mw.dispatch(req, _call_next_ok))

    assert response.status_code == 200


def test_health_exempt_from_redirect(monkeypatch):
    monkeypatch.setattr(
        security_headers,
        "settings",
        dataclasses.replace(real_settings, force_https=True),
    )

    async def noop(scope, receive, send):
        pass

    mw = security_headers.HttpsRedirectMiddleware(noop)
    response = asyncio.run(mw.dispatch(_make_request("/health"), _call_next_ok))

    assert response.status_code == 200


# --- Running-server tests (dev mode) ---

def test_dev_health_has_no_hsts():
    try:
        r = httpx.get(f"{BASE}/health", timeout=2.0)
    except httpx.ConnectError:
        pytest.skip("backend not running")

    assert r.status_code == 200
    assert "strict-transport-security" not in r.headers


def test_dev_endpoint_does_not_redirect():
    try:
        r = httpx.get(f"{BASE}/docs", timeout=2.0, follow_redirects=False)
    except httpx.ConnectError:
        pytest.skip("backend not running")

    assert r.status_code == 200
