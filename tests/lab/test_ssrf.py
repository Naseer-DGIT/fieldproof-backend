"""Lab test: SSRF on GET /lab/ssrf/fetch.

The test client uses a 20s timeout. The server's fetch timeout is 5s
(see app/lab/ssrf.py). Unreachable targets take the full 5s before the
server responds; the client must wait longer than that.

Run only with RUN_LAB_TESTS=1 against a lab-mode backend.
"""

import os
import sys

import httpx
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

BASE = os.getenv("BASE_URL", "http://localhost:8000/api/v1")
INTERNAL = "http://127.0.0.1:8000/health"

# Must exceed the server's own fetch timeout (5s) plus network latency.
CLIENT_TIMEOUT = 20.0

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_LAB_TESTS") != "1",
    reason="lab tests run only with RUN_LAB_TESTS=1",
)


def _fetch(url: str) -> httpx.Response:
    return httpx.get(
        f"{BASE}/lab/ssrf/fetch",
        params={"url": url},
        timeout=CLIENT_TIMEOUT,
    )


def test_ssrf_to_loopback_is_blocked():
    """The critical test.

    BEFORE fix: status 200 and body contains the health JSON → FAILS.
    AFTER fix: status 400 with a private-address rejection → PASSES.
    """
    r = _fetch(INTERNAL)

    if r.status_code == 200:
        body = r.json().get("body", "")
        if "ok" in body or "environment" in body:
            pytest.fail(
                f"SSRF: server fetched its own /health. body={body!r}"
            )

    assert r.status_code == 400, (
        f"expected 400 after the fix, got {r.status_code}: {r.text}"
    )
    detail = r.json().get("detail", "").lower()
    assert any(
        word in detail for word in ("private", "loopback", "blocked")
    ), f"expected a private-address rejection, got: {r.json()}"


def test_ssrf_to_rfc1918_is_blocked():
    """10.0.0.1 is in the private range. After the fix, rejected before
    the fetch attempt."""
    r = _fetch("http://10.0.0.1/")

    if r.status_code == 200:
        pytest.fail("SSRF: server reached a private address")
    assert r.status_code == 400, r.text


def test_ssrf_to_cloud_metadata_is_blocked():
    """169.254.169.254 is the link-local metadata address."""
    r = _fetch("http://169.254.169.254/latest/meta-data/")

    if r.status_code == 200:
        pytest.fail("SSRF: server reached the cloud metadata address")
    assert r.status_code == 400, r.text
