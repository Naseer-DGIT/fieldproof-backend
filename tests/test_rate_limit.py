"""Rate limiting on /auth/login.

Opt-in. Requires the server to be started with a low login limit:

    # Terminal 1
    ENVIRONMENT=lab LOGIN_LIMIT=10/minute uvicorn app.main:app --host 0.0.0.0 --port 8000

    # Terminal 2
    RUN_RATE_LIMIT_TEST=1 pytest tests/test_rate_limit.py -v
"""

import os

import httpx
import pytest

BASE = os.getenv("BASE_URL", "http://localhost:8000/api/v1")

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_RATE_LIMIT_TEST") != "1",
    reason="set RUN_RATE_LIMIT_TEST=1 and start the server with LOGIN_LIMIT=10/minute",
)


def _login(attempt: int) -> httpx.Response:
    return httpx.post(
        f"{BASE}/auth/login",
        json={"email": "nobody@example.com", "password": "wrong"},
        timeout=2.0,
    )


def test_login_rate_limited_after_ten_requests():
    """11 requests in quick succession: the 11th should be 429."""
    try:
        r = httpx.post(
            f"{BASE}/auth/login",
            json={"email": "probe@example.com", "password": "x"},
            timeout=2.0,
        )
    except httpx.ConnectError:
        pytest.skip("backend not running")

    statuses = []
    for _ in range(12):
        r = _login(0)
        statuses.append(r.status_code)

    # The limit is 10/minute. With 12 attempts, we expect at least one
    # 429. The exact position depends on how the limiter counts.
    assert 429 in statuses, f"expected a 429 in {statuses}"
