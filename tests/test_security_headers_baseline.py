"""Baseline security headers tests."""

import os

import httpx
import pytest

BASE = os.getenv("BASE_URL", "http://localhost:8000/api/v1")
HOST_ROOT = BASE.rsplit("/api/v1", 1)[0]


def _get(path: str) -> httpx.Response:
    try:
        return httpx.get(f"{HOST_ROOT}{path}", timeout=2.0)
    except httpx.ConnectError:
        pytest.skip("backend not running")


def test_health_has_nosniff():
    r = _get("/health")
    assert r.headers.get("x-content-type-options") == "nosniff"


def test_health_has_frame_deny():
    r = _get("/health")
    assert r.headers.get("x-frame-options") == "DENY"


def test_health_has_referrer_policy():
    r = _get("/health")
    assert r.headers.get("referrer-policy") == "no-referrer"


def test_health_has_csp():
    r = _get("/health")
    csp = r.headers.get("content-security-policy", "")
    assert "default-src 'none'" in csp


def test_404_also_has_headers():
    """Security headers must be present on error responses too."""
    r = _get("/does-not-exist")
    assert r.status_code == 404
    assert r.headers.get("x-content-type-options") == "nosniff"
