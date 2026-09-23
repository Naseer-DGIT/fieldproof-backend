"""Lab: SSRF — FIXED version.

The vulnerable version fetched any URL. The fix:
  - allows only http and https schemes
  - resolves the hostname
  - rejects if any resolved address is private, loopback, link-local,
    multicast, reserved, or unspecified

Checking the resolved IP rather than the hostname string matters:
`http://internal.example.com/` may resolve to 10.0.0.5, and
`http://127.0.0.1.nip.io/` resolves to 127.0.0.1 by design.

CWE-918, OWASP API7:2023 Server Side Request Forgery.
"""

import ipaddress
import socket
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, HTTPException, Query, status

router = APIRouter(prefix="/lab/ssrf", tags=["lab"])

ALLOWED_SCHEMES = {"http", "https"}
FETCH_TIMEOUT = 2.0


def _resolve(hostname: str) -> list[str]:
    try:
        infos = socket.getaddrinfo(hostname, None, proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        return []
    return list({info[4][0] for info in infos})


def _is_private(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return True

    return (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_multicast
        or addr.is_reserved
        or addr.is_unspecified
    )


def validate_url(url: str) -> str:
    parsed = urlparse(url)

    if parsed.scheme not in ALLOWED_SCHEMES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"scheme {parsed.scheme!r} is not allowed",
        )

    hostname = parsed.hostname
    if not hostname:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="url has no hostname",
        )

    addresses = _resolve(hostname)
    if not addresses:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"cannot resolve {hostname!r}",
        )

    for ip in addresses:
        if _is_private(ip):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"target resolves to a private address ({ip})",
            )

    return url


@router.get("/fetch")
async def fetch_url(
    url: str = Query(..., max_length=2048),
) -> dict:
    validate_url(url)

    try:
        async with httpx.AsyncClient(
            timeout=FETCH_TIMEOUT,
            follow_redirects=False,
        ) as client:
            response = await client.get(url)
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"fetch failed: {exc}",
        )

    return {
        "url": url,
        "status_code": response.status_code,
        "content_type": response.headers.get("content-type", ""),
        "body": response.text[:500],
    }
